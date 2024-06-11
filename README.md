# Apple and Swift Documentation Scrapers for visionOS Assist GPT

## Table of Contents

1. [Introduction](#introduction)
2. [Prerequisites](#prerequisites)
3. [Scripts](#scripts)
   - [create_appledocumentation_data.py](#create_appledocumentation_datapy)
   - [create_codesamples_data.py](#create_codesamples_datapy)
   - [create_swift_doc.py](#create_swift_docpy)
4. [Note on Usage](#note-on-usage)

## Introduction

This repository contains three Python scripts designed to scrape content from Apple's Developer Documentation and the Swift programming language documentation. These scripts were specifically created to build a comprehensive knowledge base for visionOS Assist, a specialized GPT (Generative Pre-trained Transformer) focused on Apple's visionOS development.

visionOS Assist is available at: https://chatgpt.com/g/g-gqbgzzw40-visionos-assist

The primary goal of these scripts is to gather and process the latest documentation and code samples related to visionOS, SwiftUI, RealityKit, and other relevant Apple technologies. By automating the collection of this information, we ensure that visionOS Assist has access to the most up-to-date and accurate information, enabling it to provide high-quality assistance to developers working with visionOS.

These tools offer flexible output options and customizable scraping parameters, making them valuable not only for maintaining visionOS Assist but also for developers, researchers, and documentation enthusiasts who may want to create their own knowledge bases or conduct analysis on Apple's documentation.

## Prerequisites

Before running any of the scripts, ensure you have the following installed:
- Python 3.6 or higher
- Required Python packages (install using `pip install -r requirements.txt`):
  - selenium
  - beautifulsoup4
  - webdriver_manager
  - tqdm
  - requests (for create_codesamples_data.py only)

## Scripts

### create_appledocumentation_data.py

This script scrapes content from Apple's Developer Documentation website.

#### Usage

Run the script from the command line:

```
python create_appledocumentation_data.py [arguments]
```

#### Available Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--log-level` | WARNING | Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| `--no-headless` | - | Disable headless mode for the browser |
| `--max-workers` | 4 | Set the maximum number of worker threads |
| `--timeout` | 30 | Set the timeout (in seconds) for waiting for main element |
| `--max-pages` | 0 | Set the maximum number of pages to scrape (0 for unlimited) |
| `--output-dir` | data | Set the output directory for scraped data |
| `--merged-output` | documentation | Set the filename (without extension) for the merged output |
| `--output-format` | txt | Choose the output format: txt or csv |

#### Output

- Creates individual files for each framework in the specified output directory.
- Generates a merged file containing all the scraped data.
- For TXT format: Each file contains formatted text data.
- For CSV format: Each file is a CSV with columns for framework, url, category, title, abstract, platforms, code, and content.

### create_codesamples_data.py

This script focuses on extracting code samples from Apple's Developer Documentation.

#### Usage

Run the script from the command line:

```
python create_codesamples_data.py [arguments]
```


#### Available Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--log-level` | WARNING | Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| `--no-headless` | True | Disable headless mode for the browser |
| `--timeout` | 30 | Set the timeout (in seconds) for waiting for main element |
| `--download-timeout` | 120 | Set the timeout (in seconds) for downloading files |
| `--output-format` | txt | Choose the output format: txt or csv |

#### Output

- Creates a file in the current directory with the scraped code samples.
- For TXT format: Each code sample is formatted with fields for url, title, description, code_title, and code_sample.
- For CSV format: The file has columns for url, title, description, code_title, and code_sample.

### create_swift_doc.py

This script scrapes content from the Swift programming language documentation website.

#### Usage

Run the script from the command line:

```
python create_swift_doc.py [arguments]
```

#### Available Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--output` | swift_documentation | Set the output file name (without extension) |
| `--format` | txt | Choose the output format: txt or csv |
| `--max-workers` | 5 | Set the maximum number of concurrent workers |
| `--timeout` | 30 | Set the timeout (in seconds) for page loading |

#### Output

- Creates a file in the current directory with the scraped documentation content.
- For TXT format: The file is named `[output].txt` and contains formatted text with URL and content for each page.
- For CSV format: The file is named `[output].csv` and has two columns: 'url' and 'content'.