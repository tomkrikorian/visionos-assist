import os
import glob
import logging
import argparse
import csv

from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, urljoin
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from tqdm import tqdm

# Default Configuration
DEFAULT_CONFIG = {
    "LOGGING_LEVEL": logging.WARNING,
    "HEADLESS_MODE": True,
    "MAX_WORKERS": 4,
    "MAIN_ELEMENT_TIMEOUT": 30,
    "MAX_PAGES": 0,  # Set to 0 for unlimited pages
    "OUTPUT_DIR": "data",
    "MERGED_OUTPUT_FILE": "documentation",
    "OUTPUT_FORMAT": "txt"
}

def parse_arguments():
    parser = argparse.ArgumentParser(description="Web scraper for Apple Developer Documentation")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                        default="WARNING", help="Set the logging level")
    parser.add_argument("--no-headless", action="store_false", dest="headless_mode",
                        help="Disable headless mode for the browser")
    parser.add_argument("--max-workers", type=int, default=4,
                        help="Set the maximum number of worker threads")
    parser.add_argument("--timeout", type=int, default=30,
                        help="Set the timeout for waiting for main element")
    parser.add_argument("--max-pages", type=int, default=0,
                        help="Set the maximum number of pages to scrape (0 for unlimited)")
    parser.add_argument("--output-dir", default="data",
                        help="Set the output directory for scraped data")
    parser.add_argument("--merged-output", default="documentation",
                        help="Set the filename (without extension) for the merged output")
    parser.add_argument("--output-format", choices=["txt", "csv"], default="txt",
                        help="Choose the output format: txt or csv")
    return parser.parse_args()

def update_config_from_args(args):
    config = DEFAULT_CONFIG.copy()
    config["LOGGING_LEVEL"] = getattr(logging, args.log_level)
    config["HEADLESS_MODE"] = args.headless_mode
    config["MAX_WORKERS"] = args.max_workers
    config["MAIN_ELEMENT_TIMEOUT"] = args.timeout
    config["MAX_PAGES"] = args.max_pages
    config["OUTPUT_DIR"] = args.output_dir
    config["MERGED_OUTPUT_FILE"] = args.merged_output
    config["OUTPUT_FORMAT"] = args.output_format
    return config

def setup_webdriver(headless_mode):
    options = webdriver.ChromeOptions()
    if headless_mode:
        options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    
    service = Service(ChromeDriverManager().install(), service_log_path=os.devnull)
    return webdriver.Chrome(service=service, options=options)

def extract_framework_name(url):
    return urlparse(url).path.strip('/').split('/')[1]

def format_data_to_text(data):
    return "\n".join(
        f"framework: {item['framework']}\n"
        f"url: {item['url']}\n"
        f"category: {item['category']}\n"
        f"title: {item['title']}\n"
        f"abstract: {item['abstract']}\n"
        f"platforms: {item['platforms']}\n"
        f"code: {item['code']}\n"
        f"content:\n" + "\n".join(f"  {line}" for line in item['content'].split('\n'))
        for item in data
    )

def fetch_content(driver, main_url, url, visited_urls):
    if url in visited_urls:
        return [], [], ''

    visited_urls.add(url)
    try:
        driver.get(url)
        WebDriverWait(driver, CONFIG["MAIN_ELEMENT_TIMEOUT"]).until(
            EC.presence_of_element_located((By.TAG_NAME, "main"))
        )

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        main_content = soup.find('main')
        if not main_content:
            logging.warning(f"No main content found for {url}")
            return [], [], ''

        title_element = main_content.find('h1', class_='title')
        title = title_element.find('span').get_text(strip=True) if title_element else "No Title Found"

        data = [{
            'framework': extract_framework_name(main_url),
            'url': url,
            'category': main_content.find(class_='eyebrow').get_text(strip=True) if main_content.find(class_='eyebrow') else "No Category Found",
            'title': title,
            'abstract': main_content.find(class_='abstract content').get_text(strip=True) if main_content.find(class_='abstract content') else "No Abstract Found",
            'platforms': ', '.join(span.text.strip() for span in main_content.find_all('span', class_='platform')),
            'code': main_content.find('section', class_='declaration').find('div', class_='declaration-source-wrapper').get_text(strip=True) if main_content.find('section', class_='declaration') else "No Code Found",
            'content': main_content.find('div', class_='container').get_text(strip=True) if main_content.find('div', class_='container') else "No Content Found"
        }]

        sub_urls = [
            urljoin('https://developer.apple.com', a['href'])
            for a in main_content.find_all('a', href=True)
            if a['href'].startswith('/documentation') and '#' not in a['href']
            and urljoin('https://developer.apple.com', a['href']).startswith(main_url)
            and urljoin('https://developer.apple.com', a['href']) not in visited_urls
        ]

        return data, sub_urls, format_data_to_text(data) if CONFIG["OUTPUT_FORMAT"] == "txt" else data

    except Exception as e:
        logging.error(f"Error fetching content from {url}: {str(e)}")
        return [], [], ''

def save_main_content(url, max_pages=None):
    global CONFIG
    if max_pages is None:
        max_pages = CONFIG["MAX_PAGES"]
    
    framework_name = extract_framework_name(url)
    filename = os.path.join(CONFIG["OUTPUT_DIR"], f'{framework_name.lower()}.{CONFIG["OUTPUT_FORMAT"]}')
    
    if os.path.exists(filename):
        logging.info(f"Skipping {url}, file already exists")
        return
    
    to_visit = [url]
    visited_urls = set()
    pages_processed = 0
    
    with setup_webdriver(CONFIG["HEADLESS_MODE"]) as driver:
        with tqdm(total=len(to_visit), desc=f"Processing {url}") as pbar:
            if CONFIG["OUTPUT_FORMAT"] == "csv":
                with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=['framework', 'url', 'category', 'title', 'abstract', 'platforms', 'code', 'content'])
                    writer.writeheader()
                    while to_visit and (max_pages == 0 or pages_processed < max_pages):
                        current_url = to_visit.pop(0)
                        if current_url in visited_urls:
                            continue
                        page_data, sub_urls, _ = fetch_content(driver, url, current_url, visited_urls)
                        if page_data:
                            writer.writerows(page_data)
                            pages_processed += 1
                            to_visit.extend(sub_urls)
                            pbar.total = len(to_visit)
                            pbar.update(1)
            else:  # txt format
                with open(filename, 'w', encoding='utf-8') as txtfile:
                    while to_visit and (max_pages == 0 or pages_processed < max_pages):
                        current_url = to_visit.pop(0)
                        if current_url in visited_urls:
                            continue
                        _, sub_urls, formatted_text = fetch_content(driver, url, current_url, visited_urls)
                        if formatted_text:
                            txtfile.write(formatted_text)
                            txtfile.write('\n')
                            pages_processed += 1
                            to_visit.extend(sub_urls)
                            pbar.total = len(to_visit)
                            pbar.update(1)

def merge_files():
    all_filenames = glob.glob(os.path.join(CONFIG["OUTPUT_DIR"], f'*.{CONFIG["OUTPUT_FORMAT"]}'))
    if not all_filenames:
        logging.warning("No files found to merge")
        return

    output_file = f"{CONFIG['MERGED_OUTPUT_FILE']}.{CONFIG['OUTPUT_FORMAT']}"
    
    if CONFIG["OUTPUT_FORMAT"] == "csv":
        with open(output_file, 'w', newline='', encoding='utf-8') as outfile:
            writer = None
            for filename in all_filenames:
                with open(filename, 'r', newline='', encoding='utf-8') as infile:
                    reader = csv.DictReader(infile)
                    if not writer:
                        writer = csv.DictWriter(outfile, fieldnames=reader.fieldnames)
                        writer.writeheader()
                    for row in reader:
                        writer.writerow(row)
    else:  # txt format
        with open(output_file, 'w', encoding='utf-8') as outfile:
            for filename in all_filenames:
                with open(filename, 'r', encoding='utf-8') as infile:
                    outfile.write(infile.read())
                    outfile.write('\n')

def main():
    global CONFIG
    args = parse_arguments()
    CONFIG = update_config_from_args(args)

    # Set up logging
    logging.basicConfig(level=CONFIG["LOGGING_LEVEL"], format='%(asctime)s - %(levelname)s - %(message)s')

    urls = list(set(url.lower() for url in [
        'https://developer.apple.com/documentation/avfoundation',
        'https://developer.apple.com/documentation/shadergraph',
        'https://developer.apple.com/documentation/visionos/',
        'https://developer.apple.com/documentation/TabletopKit',
        'https://developer.apple.com/documentation/AVKit',
        'https://developer.apple.com/documentation/Xcode',
        'https://developer.apple.com/documentation/healthkit',
        'https://developer.apple.com/documentation/spatial',
        'https://developer.apple.com/documentation/mapkit',
        'https://developer.apple.com/documentation/GroupActivities',
        'https://developer.apple.com/documentation/metal',
        'https://developer.apple.com/documentation/realitykit',
        'https://developer.apple.com/documentation/arkit',
        'https://developer.apple.com/documentation/cloudkit',
        'https://developer.apple.com/documentation/visionos-release-notes',
        'https://developer.apple.com/documentation/Xcode-Release-Notes',
        'https://developer.apple.com/documentation/symbols',
        'https://developer.apple.com/documentation/Accessibility',
        'https://developer.apple.com/documentation/AppIntents',
        'https://developer.apple.com/documentation/swiftui',
        'https://developer.apple.com/documentation/uikit'
    ]))

    os.makedirs(CONFIG["OUTPUT_DIR"], exist_ok=True)

    with ThreadPoolExecutor(max_workers=CONFIG["MAX_WORKERS"]) as executor:
        list(executor.map(save_main_content, urls))

    merge_files()

if __name__ == "__main__":
    main()