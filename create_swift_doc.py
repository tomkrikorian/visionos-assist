import argparse
import logging
import csv

from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin
from dataclasses import dataclass
from typing import List, Optional, Dict
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from tqdm import tqdm

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

@dataclass
class Config:
    OUTPUT: str = "swift_documentation"
    FORMAT: str = "txt"
    MAX_WORKERS: int = 5
    TIMEOUT: int = 30
    HEADLESS: bool = True

def parse_arguments() -> Config:
    parser = argparse.ArgumentParser(description="Swift Documentation Scraper")
    parser.add_argument("--output", default="swift_documentation", help="Output file name (without extension)")
    parser.add_argument("--format", choices=["txt", "csv"], default="txt", help="Output format (txt or csv)")
    parser.add_argument("--max-workers", type=int, default=5, help="Maximum number of concurrent workers")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout for page loading in seconds")
    parser.add_argument("--no-headless", action="store_false", dest="headless", help="Disable headless mode for the browser")
    
    args = parser.parse_args()
    
    return Config(
        OUTPUT=args.output,
        FORMAT=args.format,
        MAX_WORKERS=args.max_workers,
        TIMEOUT=args.timeout,
        HEADLESS=args.headless
    )

def setup_driver(config: Config) -> webdriver.Chrome:
    chrome_options = Options()
    if config.HEADLESS:
        chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

def get_links(driver: webdriver.Chrome, url: str, base_url: str, timeout: int) -> List[str]:
    driver.get(url)
    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, 'main')))
    links = driver.find_elements(By.TAG_NAME, 'a')
    return [link.get_attribute('href') for link in links 
            if link.get_attribute('href') 
            and link.get_attribute('href').startswith(base_url) 
            and '#' not in link.get_attribute('href')]

def get_content(driver: webdriver.Chrome, url: str, timeout: int) -> Optional[str]:
    driver.get(url)
    try:
        main_element = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, 'main')))
        content = main_element.text
        return content
    except Exception as e:
        logging.error(f"Error getting content from {url}: {str(e)}")
        return None

def write_content_txt(file, url: str, content: str):
    file.write(f"URL: {url}\n\n")
    file.write(content)
    file.write("\n\n" + "="*80 + "\n\n")

def write_content_csv(writer, url: str, content: str):
    writer.writerow([url, content])

def process_url(driver: webdriver.Chrome, url: str, base_url: str, output_file: str, format: str, timeout: int) -> List[str]:
    content = get_content(driver, url, timeout)
    if content:
        if format == 'txt':
            with open(output_file, 'a', encoding='utf-8') as f:
                write_content_txt(f, url, content)
        elif format == 'csv':
            with open(output_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                write_content_csv(writer, url, content)
    new_links = get_links(driver, url, base_url, timeout)
    return new_links

def main():
    config = parse_arguments()
    base_url = "https://docs.swift.org/swift-book/documentation/the-swift-programming-language"
    
    output_file = f"{config.OUTPUT}.{config.FORMAT}"
    
    # Initialize the output file
    if config.FORMAT == 'csv':
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['url', 'content'])
    
    driver = setup_driver(config)
    
    all_urls = set(get_links(driver, base_url, base_url, config.TIMEOUT))
    visited_urls = set()
    
    with tqdm(total=len(all_urls)) as pbar, ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as executor:
        futures = []
        for url in all_urls:
            future = executor.submit(process_url, driver, url, base_url, output_file, config.FORMAT, config.TIMEOUT)
            futures.append(future)
        
        for future in as_completed(futures):
            new_links = future.result()
            for link in new_links:
                if link not in visited_urls and link not in all_urls:
                    all_urls.add(link)
                    future = executor.submit(process_url, driver, link, base_url, output_file, config.FORMAT, config.TIMEOUT)
                    futures.append(future)
            visited_urls.add(url)
            pbar.update(1)
            pbar.total = len(all_urls)
    
    driver.quit()
    logging.info(f"Scraping completed. Output saved to {output_file}")

if __name__ == "__main__":
    main()
