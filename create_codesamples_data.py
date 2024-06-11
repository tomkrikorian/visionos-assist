import csv
import logging
import os
import time
import zipfile
import requests
import argparse

from io import BytesIO
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin

# Default Configuration
DEFAULT_CONFIG = {
    "LOGGING_LEVEL": logging.WARNING,
    "HEADLESS_MODE": True,
    "MAIN_ELEMENT_TIMEOUT": 30,
    "DOWNLOAD_TIMEOUT": 120,
    "OUTPUT_FORMAT": "txt"
}

# Set up logger
logger = logging.getLogger(__name__)

def parse_arguments():
    parser = argparse.ArgumentParser(description="Web scraper for Apple Developer Documentation")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                        default="WARNING", help="Set the logging level")
    parser.add_argument("--no-headless", action="store_false", dest="headless_mode",
                        help="Disable headless mode for the browser")
    parser.add_argument("--timeout", type=int, default=30,
                        help="Set the timeout for waiting for main element")
    parser.add_argument("--download-timeout", type=int, default=120,
                        help="Set the timeout for downloads")
    parser.add_argument("--output-format", choices=["txt", "csv"], default="txt",
                        help="Choose the output format: txt or csv")
    return parser.parse_args()

def update_config_from_args(args):
    config = DEFAULT_CONFIG.copy()
    config["LOGGING_LEVEL"] = getattr(logging, args.log_level)
    config["HEADLESS_MODE"] = args.headless_mode
    config["MAIN_ELEMENT_TIMEOUT"] = args.timeout
    config["DOWNLOAD_TIMEOUT"] = args.download_timeout
    config["OUTPUT_FORMAT"] = args.output_format
    return config

def setup_chrome_options(config):
    options = webdriver.ChromeOptions()
    if config["HEADLESS_MODE"]:
        options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    return options

def fetch_video_links(driver, main_url, config):
    logger.info(f'Fetching session links from {main_url}')
    driver.get(main_url)
    WebDriverWait(driver, config["MAIN_ELEMENT_TIMEOUT"]).until(
        EC.presence_of_element_located((By.TAG_NAME, "main"))
    )
    page_source = driver.page_source
    soup = BeautifulSoup(page_source, 'html.parser')
    session_links = [urljoin(main_url, a['href']) for a in soup.find_all('a', href=True) if 'videos/play/' in a['href']]

    # Log all found links
    for link in session_links:
        logger.info(f'Found session link: {link}')

    return session_links

def fetch_code_samples_in_videos(driver, url, config):
    logger.info(f'Processing URL: {url}')
    driver.get(url)

    try:
        # Wait until the main element is present
        WebDriverWait(driver, config["MAIN_ELEMENT_TIMEOUT"]).until(
            EC.presence_of_element_located((By.TAG_NAME, "main"))
        )
    except Exception as e:
        logger.error(f"Error while loading {url}: {e}")
        return f"Error while loading {url}: {e}"

    page_source = driver.page_source
    soup = BeautifulSoup(page_source, 'html.parser')
    main_content = soup.find('main')

    if not main_content:
        logger.error(f"No main content found for {url}")
        return f"No main content found for {url}"

    title_element = main_content.find(class_="supplement details active")
    title = title_element.find('h1').get_text(strip=True) if title_element else "No Title Found"
    description = title_element.find('p').get_text(strip=True) if title_element and title_element.find('p') else "No Description Found"
    logger.debug(f'Title found: {title}')
    logger.debug(f'Description found: {description}')

    code_samples = []
    for code_container in main_content.find_all(class_="sample-code-main-container"):
        code_title_element = code_container.find(class_="jump-to-time-sample")
        code_title = code_title_element.get_text(strip=True) if code_title_element else "No Code Title Found"
        logger.debug(f'Code title found: {code_title}')
        code_sample = '\n'.join([code.get_text(separator='\n') for code in code_container.find_all(class_='code-source')])

        if code_sample:
            code_samples.append({
                "url": url,
                "title": title,
                "description": description,
                "code_title": code_title,
                "code_sample": code_sample
            })
            logger.debug(f'Code sample found: {code_sample}')

    if not code_samples:
        code_samples.append({
            "url": url,
            "title": title,
            "description": description,
            "code_title": "No Code Title Found",
            "code_sample": "No code samples found for this URL"
        })

    return code_samples

def download_and_extract_samples(download_url, source_url, title, description, config):
    parsed_url = urlparse(source_url)
    folder_name = os.path.join('code_samples', parsed_url.path.strip('/').replace('/', '_'))

    if os.path.exists(folder_name) and os.listdir(folder_name):
        logger.info(f'Folder {folder_name} already exists and is not empty, skipping download.')
        return process_extracted_files(folder_name, source_url, title, description)

    os.makedirs(folder_name, exist_ok=True)
    logger.info(f'Downloading from {download_url}')

    try:
        response = requests.get(download_url, timeout=config["DOWNLOAD_TIMEOUT"])
        if response.status_code == 200:
            with zipfile.ZipFile(BytesIO(response.content)) as zip_file:
                zip_file.extractall(folder_name)
            return process_extracted_files(folder_name, source_url, title, description)
        else:
            logger.error(f"Failed to download {download_url} with status code {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"Error downloading {download_url}: {e}")
        return []

def extract_abstract_and_remove_comment(content):
    abstract = ""
    if content.startswith("/*"):
        end_index = content.find("*/")
        if end_index != -1:
            comment_content = content[2:end_index].strip()
            for line in comment_content.split('\n'):
                if line.strip().startswith("Abstract:"):
                    abstract = line.strip().replace("Abstract:", "").strip()
            content = content[end_index + 2:].strip()
    return abstract, content

def process_extracted_files(folder_name, source_url, title, description):
    code_samples = []

    for root, _, files in os.walk(folder_name):
        for file in files:
            if file.endswith('.swift'):
                file_path = os.path.join(root, file)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                abstract, content = extract_abstract_and_remove_comment(content)
                code_samples.append({
                    "url": source_url,
                    "title": title,
                    "description": abstract or description,
                    "code_title": file,
                    "code_sample": content
                })
                logger.info(f'Processed file: {file_path}')

    return code_samples

def process_url_list(url_list, config):
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=setup_chrome_options(config))
    all_code_samples = []
    try:
        for url in url_list:
            logger.info(f'Processing URL from list: {url}')
            driver.get(url)
            try:
                WebDriverWait(driver, config["MAIN_ELEMENT_TIMEOUT"]).until(
                    EC.presence_of_element_located((By.TAG_NAME, "main"))
                )
            except Exception as e:
                logger.error(f"Error while loading {url}: {e}")
                continue

            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            main_content = soup.find('main')

            if not main_content:
                logger.error(f"No main content found for {url}")
                continue

            title_element = main_content.find(class_="title")
            title = title_element.get_text(strip=True) if title_element else "No Title Found"
            description_element = main_content.find(class_="abstract content")
            description = description_element.get_text(strip=True) if description_element else "No Description Found"

            download_link_element = main_content.find('a', class_='sample-download')
            if download_link_element:
                download_link = urljoin(url, download_link_element['href'])
                logger.info(f'Found download link: {download_link}')
                code_samples = download_and_extract_samples(download_link, url, title, description, config)
                all_code_samples.extend(code_samples)

    finally:
        driver.quit()

    return all_code_samples

def fetch_sample_links_from_wwdc(driver, wwdc_urls, config):
    sample_links = []
    for url in wwdc_urls:
        logger.info(f'Fetching sample links from {url}')
        driver.get(url)
        WebDriverWait(driver, config["MAIN_ELEMENT_TIMEOUT"]).until(
            EC.presence_of_element_located((By.TAG_NAME, "main"))
        )
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        links = [urljoin(url, a['href']) for a in soup.find_all('a', href=True, class_='icon icon-after icon-chevronright') if 'View code' in a.text]

        # Log all found links
        for link in links:
            logger.info(f'Found sample link: {link}')
            sample_links.append(link)

    return sample_links

def save_code_samples_to_file(code_samples, config):
    if config["OUTPUT_FORMAT"] == "txt":
        with open('code_samples.txt', 'w', encoding='utf-8') as f:
            for sample in code_samples:
                f.write(f"url: {sample['url']}\n")
                f.write(f"title: {sample['title']}\n")
                f.write(f"description: {sample['description']}\n")
                f.write(f"code_title: {sample['code_title']}\n")
                f.write(f"code_sample:\n{sample['code_sample']}\n\n")
        logger.info(f'Code samples saved to code_samples.txt')
    elif config["OUTPUT_FORMAT"] == "csv":
        with open('code_samples.csv', 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=["url", "title", "description", "code_title", "code_sample"])
            writer.writeheader()
            writer.writerows(code_samples)
        logger.info(f'Code samples saved to code_samples.csv')

def main():
    args = parse_arguments()
    config = update_config_from_args(args)

    # Set up logging
    logging.basicConfig(level=config["LOGGING_LEVEL"], format='%(asctime)s - %(levelname)s - %(message)s')

    videos_url = 'https://developer.apple.com/videos/all-videos/'
    wwdc_samples_urls = [
        'https://developer.apple.com/sample-code/wwdc/2024/',
        'https://developer.apple.com/sample-code/wwdc/2023/'
    ]
    samples_list = [
        'https://developer.apple.com/documentation/visionos/world',
        'https://developer.apple.com/documentation/visionos/destination-video',
        'https://developer.apple.com/documentation/visionos/happybeam',
        'https://developer.apple.com/documentation/visionos/diorama',
        'https://developer.apple.com/documentation/visionos/swift-splash',
        'https://developer.apple.com/documentation/visionos/incorporating-real-world-surroundings-in-an-immersive-experience',
        'https://developer.apple.com/documentation/visionos/placing-content-on-detected-planes',
        'https://developer.apple.com/documentation/visionos/tracking-points-in-world-space',
        'https://developer.apple.com/documentation/avfoundation/media_reading_and_writing/converting_side-to-side_3d_video_to_multiview_hevc',
        'https://developer.apple.com/documentation/realitykit/construct-an-immersive-environment-for-visionos',
        'https://developer.apple.com/documentation/realitykit/transforming-realitykit-entities-with-gestures',
        'https://developer.apple.com/documentation/realitykit/simulating-physics-with-collisions-in-your-visionos-app',
        'https://developer.apple.com/documentation/realitykit/simulating-particles-in-your-visionos-app',
        'https://developer.apple.com/documentation/visionOS/BOT-anist',
        'https://developer.apple.com/documentation/visionos/building-an-immersive-media-viewing-experience',
        'https://developer.apple.com/documentation/visionos/enabling-video-reflections-in-an-immersive-environment',
        'https://developer.apple.com/documentation/visionos/exploring_object_tracking_with_arkit',
        'https://developer.apple.com/documentation/realitykit/composing-interactive-3d-content-with-realitykit-and-reality-composer-pro',
        'https://developer.apple.com/documentation/realitykit/presenting-an-artists-scene',
        'https://developer.apple.com/documentation/realitykit/creating-a-spatial-drawing-app-with-realitykit',
        'https://developer.apple.com/documentation/realitykit/combining-2d-and-3d-views-in-an-immersive-app',
        'https://developer.apple.com/documentation/realitykit/creating-a-spaceship-game',
        'https://developer.apple.com/documentation/realitykit/rendering-a-windowed-game-in-stereo',
        'https://developer.apple.com/documentation/arkit/arkit_in_visionos/building_local_experiences_with_room_tracking',
        'https://developer.apple.com/documentation/healthkit/visualizing_healthkit_state_of_mind_in_visionos'
    ]

    main_start_time = time.time()

    # Process the session links
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=setup_chrome_options(config))
    try:
        session_links = fetch_video_links(driver, videos_url, config)

        all_code_samples = []
        for link in session_links:
            code_samples = fetch_code_samples_in_videos(driver, link, config)
            all_code_samples.extend(code_samples)

        # Fetch sample links from WWDC sample code URLs
        wwdc_sample_links = fetch_sample_links_from_wwdc(driver, wwdc_samples_urls, config)
        for link in wwdc_sample_links:
            if link not in samples_list:
                samples_list.append(link)

    finally:
        driver.quit()

    # Process the additional URL list
    all_code_samples.extend(process_url_list(samples_list, config))

    # Save code samples to file
    save_code_samples_to_file(all_code_samples, config)

    main_end_time = time.time()
    logger.info(f'Total execution time: {main_end_time - main_start_time:.2f} seconds')

if __name__ == "__main__":
    main()