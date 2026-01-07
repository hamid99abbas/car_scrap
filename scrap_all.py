"""
Complete Car Valuation Bot - Multi-Platform Support with Email & Scheduling
Scrapes PistonHeads + AutoTrader -> Detects plates -> Gets valuations -> Sends email report
Uses ORIGINAL WORKING CODE for cookie handling
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import time
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException
import logging
from datetime import datetime
import sys
import csv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('car_valuation_bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class EmailReporter:
    """Handle email sending"""

    def __init__(self, sender_email, sender_password, smtp_server='smtp.gmail.com', smtp_port=587):
        """
        Initialize email reporter
        sender_email: your Gmail address
        sender_password: your Gmail app password (NOT regular password)
        """
        self.sender_email = sender_email
        self.sender_password = sender_password
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port

    def send_report(self, recipient_email, results, json_file='car_valuations_results.json',
                    csv_file='car_valuations_results.csv'):
        """Send email report with attachments"""
        try:
            logger.info("\n" + "=" * 70)
            logger.info("SENDING EMAIL REPORT")
            logger.info("=" * 70)

            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.sender_email
            msg['To'] = recipient_email
            msg['Subject'] = f"🚗 Car Valuation Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}"

            # Generate HTML body
            html_body = self._generate_html_report(results)
            msg.attach(MIMEText(html_body, 'html'))

            # Attach JSON file
            try:
                with open(json_file, 'rb') as attachment:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment.read())
                    encoders.encode_base64(part)
                    part.add_header('Content-Disposition', f'attachment; filename= {json_file}')
                    msg.attach(part)
                    logger.info(f"✓ Attached {json_file}")
            except FileNotFoundError:
                logger.warning(f"⚠ {json_file} not found, skipping attachment")

            # Attach CSV file
            try:
                with open(csv_file, 'rb') as attachment:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment.read())
                    encoders.encode_base64(part)
                    part.add_header('Content-Disposition', f'attachment; filename= {csv_file}')
                    msg.attach(part)
                    logger.info(f"✓ Attached {csv_file}")
            except FileNotFoundError:
                logger.warning(f"⚠ {csv_file} not found, skipping attachment")

            # Send email
            logger.info(f"Sending to {recipient_email}...")
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)

            logger.info(f"✓ Email sent successfully to {recipient_email}")
            logger.info("=" * 70)
            return True

        except Exception as e:
            logger.error(f"✗ Error sending email: {e}")
            logger.info("=" * 70)
            return False

    def _generate_html_report(self, results):
        """Generate HTML email report"""
        total = len(results)
        plates_detected = sum(1 for c in results if c.get('detected_plate') != "Not detected")
        valuations = sum(1 for c in results if c.get('webuyanycar_valuation')
                         not in ["Failed", "Error", "No plate/mileage", "No plate or mileage"])

        source_counts = {}
        for car in results:
            source = car.get('source', 'Unknown')
            source_counts[source] = source_counts.get(source, 0) + 1

        source_html = "".join([f"<li>{src}: {count}</li>" for src, count in source_counts.items()])

        cars_html = ""
        for i, car in enumerate(results[:20], 1):
            link = car.get('link', '#')
            link_html = f'<a href="{link}" target="_blank" style="color: #3498db; text-decoration: none;">View</a>' if link and link != '#' else 'N/A'
            cars_html += f"""
            <tr>
                <td>{i}</td>
                <td>{car.get('source', '?')}</td>
                <td>{car.get('title', 'N/A')[:40]}</td>
                <td>{car.get('price', 'N/A')}</td>
                <td>{car.get('mileage', 'N/A')}</td>
                <td>{car.get('detected_plate', 'N/A')}</td>
                <td>{car.get('webuyanycar_valuation', 'N/A')}</td>
                <td>{link_html}</td>
            </tr>
            """

        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; color: #333; }}
                .header {{ background-color: #2c3e50; color: white; padding: 20px; border-radius: 5px; }}
                .summary {{ background-color: #ecf0f1; padding: 15px; margin: 20px 0; border-left: 4px solid #3498db; }}
                .stats {{ display: flex; gap: 20px; margin: 15px 0; }}
                .stat-box {{ background-color: #3498db; color: white; padding: 15px; border-radius: 5px; flex: 1; text-align: center; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th, td {{ border: 1px solid #bdc3c7; padding: 10px; text-align: left; }}
                th {{ background-color: #34495e; color: white; }}
                tr:nth-child(even) {{ background-color: #ecf0f1; }}
                .footer {{ color: #7f8c8d; font-size: 12px; margin-top: 30px; text-align: center; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🚗 Car Valuation Report</h1>
                <p>Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>

            <div class="summary">
                <h2>Summary</h2>
                <div class="stats">
                    <div class="stat-box">
                        <h3>{total}</h3>
                        <p>Total Cars</p>
                    </div>
                    <div class="stat-box">
                        <h3>{plates_detected}</h3>
                        <p>Plates Detected</p>
                    </div>
                    <div class="stat-box">
                        <h3>{valuations}</h3>
                        <p>Valuations Obtained</p>
                    </div>
                </div>

                <h3>By Source</h3>
                <ul>{source_html}</ul>
            </div>

            <h2>Top Results (showing {min(20, total)} of {total})</h2>
            <table>
                <tr>
                    <th>#</th>
                    <th>Source</th>
                    <th>Title</th>
                    <th>Price</th>
                    <th>Mileage</th>
                    <th>Plate</th>
                    <th>Valuation</th>
                    <th>Link</th>
                </tr>
                {cars_html}
            </table>

            <div class="footer">
                <p>Full detailed results attached as JSON and CSV files</p>
                <p>For questions or issues, check the log file: car_valuation_bot.log</p>
            </div>
        </body>
        </html>
        """

        return html


class CarValuationBot:
    def __init__(self, ocr_api_key='K87899142388957', headless=False):
        self.ocr_api_key = ocr_api_key
        self.headless = headless
        self.results = []

    def extract_images_from_detail_page(self, driver, url, max_images=10):
        """Extract images from AutoTrader detail page - EXACT ORIGINAL CODE"""
        images = []
        try:
            driver.execute_script("window.open(arguments[0]);", url)
            driver.switch_to.window(driver.window_handles[-1])

            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "img"))
            )
            time.sleep(2)

            img_elements = driver.find_elements(By.CSS_SELECTOR, "img")

            for img in img_elements:
                for attr in ['src', 'data-src', 'data-lazy-src']:
                    try:
                        src = img.get_attribute(attr)
                        if (src and
                                src.startswith('http') and
                                'placeholder' not in src.lower() and
                                'logo' not in src.lower() and
                                'icon' not in src.lower()):
                            images.append(src)
                            break
                    except:
                        continue
        except Exception as e:
            logger.debug(f"Error loading detail page: {str(e)[:50]}")
        finally:
            try:
                driver.close()
                driver.switch_to.window(driver.window_handles[0])
            except:
                pass

        return list(dict.fromkeys(images))[:max_images]

    def scrape_autotrader(self, url, max_cars=None):
        """Scrape AutoTrader - EXACT ORIGINAL WORKING CODE"""
        logger.info("=" * 70)
        logger.info("SCRAPING CARS FROM AUTOTRADER")
        logger.info("=" * 70)

        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.binary_location = '/usr/bin/google-chrome'
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument(
            'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        chrome_options.add_argument('--window-size=1920,1080')

        driver = None
        cars = []
        seen_titles = set()

        try:
            driver = webdriver.Chrome(options=chrome_options)

            logger.info("Loading AutoTrader page...")
            driver.get(url)
            time.sleep(10)

            # Accept cookies - ORIGINAL CODE APPROACH
            try:
                cookie_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//button[contains(text(), 'Accept') or contains(text(), 'accept')]"))
                )
                cookie_button.click()
                logger.info("✓ Accepted cookies")
                time.sleep(2)
            except:
                logger.info("No cookie banner found")

            logger.info("Scrolling to load listings...")
            last_count = 0
            for i in range(15):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)

                current_listings = driver.find_elements(By.CSS_SELECTOR, "li[data-advert-id], article")
                current_count = len(current_listings)

                if i % 3 == 0:
                    logger.info(f"Scroll {i + 1}/15... (found {current_count} elements)")

                if current_count == last_count and i > 5:
                    logger.info(f"✓ All content loaded at scroll {i + 1}")
                    break

                last_count = current_count

            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            logger.info("\nExtracting car data...\n")

            all_selectors = [
                "li[data-advert-id]",
                "li[data-testid='trader-seller-listing']",
                "article[data-testid='trader-seller-listing']",
                "section[data-testid='trader-seller-listing']",
                "li.search-page__result",
                "article.product-card",
            ]

            listings = []
            for selector in all_selectors:
                try:
                    found = driver.find_elements(By.CSS_SELECTOR, selector)
                    if found and len(found) > len(listings):
                        listings = found
                        logger.info(f"✓ Using selector: {selector} ({len(found)} elements)")
                except:
                    continue

            if len(listings) <= 1:
                logger.info("Trying broader search...")
                articles = driver.find_elements(By.TAG_NAME, "article")
                sections = driver.find_elements(By.TAG_NAME, "section")

                potential_listings = []
                for elem in articles + sections:
                    text = elem.text.lower()
                    if ('£' in elem.text and
                            any(word in text for word in ['miles', 'manual', 'automatic', 'petrol', 'diesel']) and
                            not any(word in text for word in ['make and model', 'postcode', 'search radius'])):
                        potential_listings.append(elem)

                if len(potential_listings) > len(listings):
                    listings = potential_listings
                    logger.info(f"✓ Found {len(listings)} potential car listings")

            if max_cars:
                listings = listings[:max_cars]
                logger.info(f"✓ Limited to first {max_cars} cars\n")

            logger.info(f"Processing {len(listings)} AutoTrader listings...\n")

            for idx, listing in enumerate(listings):
                try:
                    listing_text = listing.text

                    if not listing_text or len(listing_text) < 20:
                        continue

                    if any(skip in listing_text.lower() for skip in
                           ['make and model', 'search radius', 'postcode', 'price range']):
                        continue

                    car = {'source': 'AutoTrader'}

                    title_text = None
                    title_selectors = [
                        "h3", "h2", "a[href*='/car-details']",
                        "[data-testid='search-listing-title']", "p[class*='title']"
                    ]

                    for selector in title_selectors:
                        try:
                            title_elem = listing.find_element(By.CSS_SELECTOR, selector)
                            title_text = title_elem.text.strip()
                            if title_text and len(title_text) > 10:
                                break
                        except:
                            continue

                    if not title_text:
                        lines = listing_text.split('\n')
                        for line in lines[:5]:
                            if 10 < len(line) < 100 and not line.startswith('£'):
                                if any(word in line.lower() for word in
                                       ['euro', 'sport', 'edition', 'comfort', 'life', 'style']):
                                    title_text = line.strip()
                                    break

                    if title_text:
                        car['title'] = title_text
                    else:
                        continue

                    price_match = re.search(r'£([\d,]+)', listing_text)
                    if price_match:
                        car['price'] = f"£{price_match.group(1)}"

                    try:
                        link_elem = listing.find_element(By.CSS_SELECTOR, "a[href*='/car-details']")
                        car['link'] = link_elem.get_attribute('href')
                    except:
                        car['link'] = None

                    year_match = re.search(r'\b(19|20)\d{2}\b', listing_text)
                    if year_match:
                        car['year'] = year_match.group()

                    mileage_match = re.search(r'([\d,]+)\s*miles?', listing_text, re.IGNORECASE)
                    if mileage_match:
                        car['mileage'] = mileage_match.group(1).replace(',', '')

                    if re.search(r'\bManual\b', listing_text, re.IGNORECASE):
                        car['transmission'] = 'Manual'
                    elif re.search(r'\bAutomatic\b', listing_text, re.IGNORECASE):
                        car['transmission'] = 'Automatic'

                    for fuel in ['Petrol', 'Diesel', 'Electric', 'Hybrid']:
                        if re.search(rf'\b{fuel}\b', listing_text, re.IGNORECASE):
                            car['fuelType'] = fuel
                            break

                    if car.get('link'):
                        logger.info(f"  → Fetching images: {car['title'][:50]}")
                        car['images'] = self.extract_images_from_detail_page(driver, car['link'], max_images=4)
                        logger.info(f"    ✓ Found {len(car['images'])} images")
                    else:
                        car['images'] = []
                        logger.info(f"  ⚠ No link: {car['title'][:50]}")

                    if car.get('title') and car.get('price'):
                        unique_key = f"{car['title'].lower().strip()}_{car.get('price', '')}"

                        if unique_key not in seen_titles:
                            seen_titles.add(unique_key)
                            cars.append(car)
                            logger.info(f"✓ {len(cars)}. {car['title'][:55]} - {car['price']}")

                except Exception as e:
                    if idx < 5:
                        logger.error(f"Error parsing listing {idx + 1}: {str(e)[:50]}")
                    continue

        except Exception as e:
            logger.error(f"AutoTrader scraping error: {e}")
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass

        logger.info(f"\n✓ Successfully scraped {len(cars)} cars from AutoTrader\n")
        return cars

    def scrape_pistonheads(self, url, min_images=2):
        """Scrape PistonHeads - EXACT ORIGINAL WORKING CODE"""
        logger.info("=" * 70)
        logger.info("SCRAPING CARS FROM PISTONHEADS")
        logger.info("=" * 70)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            logger.info("✓ Successfully fetched page")
        except Exception as e:
            logger.error(f"✗ Error fetching page: {e}")
            return []

        soup = BeautifulSoup(response.content, 'html.parser')
        listings = soup.find_all('article') or soup.find_all('div', class_=re.compile('listing|card'))

        cars = []
        seen_titles = set()

        logger.info(f"Found {len(listings)} potential listings\n")

        for listing in listings:
            try:
                car = {'source': 'PistonHeads'}

                title_elem = listing.find(['h2', 'h3', 'h4']) or listing.find('a', href=re.compile('/buy/listing/'))
                if title_elem:
                    car['title'] = title_elem.get_text(strip=True)
                else:
                    continue

                link_elem = listing.find('a', href=re.compile('/buy/listing/'))
                if link_elem and link_elem.get('href'):
                    car['link'] = urljoin('https://www.pistonheads.com', link_elem.get('href'))
                else:
                    car['link'] = None

                price_elem = listing.find(string=re.compile('£')) or listing.find(class_=re.compile('price'))
                if price_elem:
                    car['price'] = price_elem.get_text(strip=True) if hasattr(price_elem, 'get_text') else str(
                        price_elem).strip()

                images = []
                for img in listing.find_all('img'):
                    img_url = img.get('src') or img.get('data-src')
                    if img_url and 'placeholder' not in img_url.lower():
                        full_url = urljoin('https://www.pistonheads.com', img_url)
                        full_url = full_url.replace('/Thumbnail/', '/Fullsize/')
                        images.append(full_url)

                car['images'] = images[:4]

                details_text = listing.get_text()

                if match := re.search(r'([\d,]+)\s*miles?', details_text, re.IGNORECASE):
                    car['mileage'] = match.group(1).replace(',', '')

                if match := re.search(r'(\d+)\s*miles?\s*away', details_text, re.IGNORECASE):
                    car['distance'] = f"{match.group(1)} miles away"

                if car.get('title') and car.get('price') and len(car.get('images', [])) >= min_images:
                    title_key = car['title'].lower().strip()
                    if title_key not in seen_titles:
                        seen_titles.add(title_key)
                        cars.append(car)
                        logger.info(f"✓ {len(cars)}. {car['title'][:50]} ({len(car['images'])} images)")

            except Exception as e:
                logger.error(f"Error parsing listing: {e}")
                continue

        logger.info(f"\n✓ Successfully scraped {len(cars)} cars from PistonHeads\n")
        return cars

    def detect_license_plate(self, image_url, max_retries=3):
        """Detect license plate using OCR with multiple strategies"""
        if 'svg+xml' in image_url:
            return None

        for attempt in range(max_retries):
            try:
                payload = {
                    'url': image_url,
                    'apikey': self.ocr_api_key,
                    'language': 'eng',
                    'isOverlayRequired': False,
                    'detectOrientation': True,
                    'scale': True,
                    'OCREngine': 2,
                }

                response = requests.post(
                    'https://api.ocr.space/parse/image',
                    data=payload,
                    timeout=30
                )

                result = response.json()

                if result.get('IsErroredOnProcessing'):
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
                    return None

                parsed_text = result.get('ParsedResults', [{}])[0].get('ParsedText', '')
                if not parsed_text:
                    return None

                text = parsed_text.upper().replace('\n', ' ').replace('\r', ' ')

                # UK Plate Patterns (comprehensive)
                patterns = [
                    # Modern UK (2001+): AB12 CDE
                    r'\b[A-Z]{2}\d{2}\s*[A-Z]{3}\b',
                    # With separators: AB-12-CDE or AB12-CDE
                    r'\b[A-Z]{2}[-]?\d{2}\s*[-]?[A-Z]{3}\b',
                    # Old format: A123 BCD
                    r'\b[A-Z]\d{1,3}\s*[A-Z]{3}\b',
                    # Very old format: ABC 123D
                    r'\b[A-Z]{3}\s*\d{1,3}[A-Z]\b',
                    # With hyphens: A-123-BCD
                    r'\b[A-Z][-]?\d{1,3}\s*[-]?[A-Z]{3}\b',
                    # EU format with flag: EU AB12 CDE
                    r'(?:EU|GB)\s*[A-Z]{2}\d{2}\s*[A-Z]{3}',
                ]

                plates_found = []

                for pattern in patterns:
                    matches = re.findall(pattern, text)
                    for match in matches:
                        # Clean up the match
                        clean_plate = match.replace(' ', '').replace('-', '')
                        # Validate it's correct length (7 chars for UK)
                        if len(clean_plate) >= 6:  # At least 6 chars
                            plates_found.append(clean_plate)

                # Remove duplicates while preserving order
                unique_plates = []
                seen = set()
                for plate in plates_found:
                    if plate not in seen:
                        unique_plates.append(plate)
                        seen.add(plate)

                if unique_plates:
                    # Return the first valid plate found
                    return unique_plates[0]

                # If no plate found and not last attempt, retry
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue

                return None

            except Exception as e:
                logger.debug(f"OCR attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                return None

        return None

    def get_valuation(self, registration, mileage, postcode="M32 9AU"):
        """Get valuation from Webuyanycar - EXACT ORIGINAL WORKING CODE"""
        logger.info(f"  Getting valuation for {registration}...")

        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.binary_location = '/usr/bin/google-chrome'
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--log-level=3")

        driver = None

        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(30)
            wait = WebDriverWait(driver, 20)

            logger.info("    Loading homepage...")
            driver.get("https://www.webuyanycar.com/")
            time.sleep(4)

            # Handle cookies on homepage - ORIGINAL APPROACH
            cookie_accepted = False

            try:
                cookie_btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH,
                                                "//button[contains(text(), 'Allow all cookies')]"))
                )
                cookie_btn.click()
                time.sleep(1)
                logger.info("    ✓ Cookies accepted (homepage)")
                cookie_accepted = True
            except:
                pass

            if not cookie_accepted:
                try:
                    cookie_btn = driver.find_element(By.XPATH,
                                                     "//button[contains(translate(text(), 'ACCEPT', 'accept'), 'accept') or "
                                                     "contains(translate(text(), 'ALLOW', 'allow'), 'allow')]")
                    if cookie_btn.is_displayed():
                        cookie_btn.click()
                        time.sleep(1)
                        logger.info("    ✓ Cookies accepted (homepage - method 2)")
                        cookie_accepted = True
                except:
                    pass

            if not cookie_accepted:
                logger.info("    ⚠ No cookie banner on homepage (will check later)")

            logger.info("    Entering registration...")
            try:
                reg_input = wait.until(EC.presence_of_element_located((By.ID, "vehicleReg")))
            except:
                try:
                    reg_input = wait.until(EC.presence_of_element_located((By.NAME, "vehicleReg")))
                except:
                    reg_input = wait.until(
                        EC.presence_of_element_located((By.XPATH, "//input[@placeholder='e.g. AB12 CDE']")))

            reg_input.clear()
            reg_input.send_keys(registration)
            time.sleep(0.5)

            logger.info("    Entering mileage...")
            try:
                mileage_input = driver.find_element(By.NAME, "Mileage")
            except:
                try:
                    mileage_input = driver.find_element(By.ID, "Mileage")
                except:
                    mileage_input = driver.find_element(By.XPATH, "//input[@placeholder='e.g. 32,000']")

            mileage_input.clear()
            mileage_input.send_keys(str(mileage))
            time.sleep(0.5)

            logger.info("    Submitting form...")
            submit_btn = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Get my car valuation')]")))
            driver.execute_script("arguments[0].scrollIntoView(true);", submit_btn)
            time.sleep(0.5)

            try:
                submit_btn.click()
            except:
                driver.execute_script("arguments[0].click();", submit_btn)

            logger.info("    Waiting for vehicle details...")
            try:
                wait.until(EC.url_contains("/vehicle/details"))
                time.sleep(2)
                logger.info("    ✓ Reached details page")
            except TimeoutException:
                logger.error("    ✗ Timeout waiting for details page")
                return None

            # Check for cookies again on details page
            if not cookie_accepted:
                logger.info("    Checking for cookie banner on details page...")

                try:
                    cookie_btn = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((By.XPATH,
                                                    "//button[contains(text(), 'Allow all cookies')]"))
                    )
                    cookie_btn.click()
                    time.sleep(1)
                    logger.info("    ✓ Cookies accepted (details page)")
                    cookie_accepted = True
                except:
                    pass

                if not cookie_accepted:
                    try:
                        cookie_btn = driver.find_element(By.XPATH,
                                                         "//button[contains(translate(text(), 'ACCEPT', 'accept'), 'accept') or "
                                                         "contains(translate(text(), 'ALLOW', 'allow'), 'allow')]")
                        if cookie_btn.is_displayed():
                            cookie_btn.click()
                            time.sleep(1)
                            logger.info("    ✓ Cookies accepted (details page - method 2)")
                            cookie_accepted = True
                    except:
                        pass

                if not cookie_accepted:
                    logger.info("    ⚠ No cookie banner found")

            logger.info("    Filling required fields...")

            try:
                email_input = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='email']")))
                driver.execute_script("arguments[0].scrollIntoView(true);", email_input)
                time.sleep(0.3)
                email_input.click()
                email_input.clear()
                email_input.send_keys("test@example.com")
                logger.info("    ✓ Email entered")
                time.sleep(0.5)
            except Exception as e:
                logger.warning(f"    ⚠ Email: {str(e)[:50]}")

            postcode_entered = False

            try:
                postcode_input = driver.find_element(By.XPATH,
                                                     "//input[contains(@placeholder, 'M71') or contains(@placeholder, 'postcode')]")
                driver.execute_script("arguments[0].scrollIntoView(true);", postcode_input)
                time.sleep(0.3)
                postcode_input.click()
                postcode_input.clear()
                postcode_input.send_keys(postcode)
                logger.info(f"    ✓ Postcode: {postcode}")
                postcode_entered = True
                time.sleep(0.5)
            except:
                pass

            if not postcode_entered:
                try:
                    postcode_input = driver.find_element(By.NAME, "postcode")
                    driver.execute_script("arguments[0].scrollIntoView(true);", postcode_input)
                    time.sleep(0.3)
                    postcode_input.click()
                    postcode_input.clear()
                    postcode_input.send_keys(postcode)
                    logger.info(f"    ✓ Postcode: {postcode}")
                    time.sleep(0.5)
                except:
                    logger.warning("    ⚠ Could not find postcode field")

            try:
                vat_no = driver.find_element(By.XPATH, "//button[normalize-space()='No']")
                driver.execute_script("arguments[0].scrollIntoView(true);", vat_no)
                time.sleep(0.3)
                vat_no.click()
                logger.info("    ✓ VAT: No")
                time.sleep(0.5)
            except:
                pass

            try:
                dropdown = driver.find_element(By.XPATH, "//select")
                if not dropdown.get_attribute("value"):
                    dropdown.click()
                    time.sleep(0.3)
                    options = driver.find_elements(By.XPATH, "//select/option")
                    if len(options) > 1:
                        options[1].click()
                        time.sleep(0.3)
            except:
                pass

            logger.info("    Looking for submit button...")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            driver.execute_script("window.scrollBy(0, -150);")
            time.sleep(0.5)

            valuation_btn = None
            buttons = driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                btn_text = btn.text.strip()
                if (
                        'Get my valuation' in btn_text or 'Get valuation' in btn_text) and btn.is_displayed() and btn.is_enabled():
                    valuation_btn = btn
                    logger.info(f"    ✓ Found: '{btn_text}'")
                    break

            if valuation_btn:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", valuation_btn)
                time.sleep(0.5)
                try:
                    valuation_btn.click()
                except:
                    driver.execute_script("arguments[0].click();", valuation_btn)

                logger.info("    Waiting for valuation...")
                time.sleep(6)

                try:
                    wait.until(lambda d: "/valuation/" in d.current_url or "/appointment" in d.current_url)
                    logger.info(f"    ✓ Valuation page loaded")
                except:
                    logger.warning("    ⚠ URL didn't change as expected")

            logger.info("    Extracting price...")
            time.sleep(2)
            elements = driver.find_elements(By.XPATH, "//*[contains(text(), '£')]")
            found_prices = []

            for elem in elements:
                text = elem.text.strip()
                if text and len(text) < 50:
                    matches = re.findall(r'£\s*\d+(?:,\d{3})*(?:\.\d{2})?', text)
                    for match in matches:
                        value = int(re.sub(r'[£,.]', '', match.split('.')[0]))
                        if 100 <= value <= 50000:
                            found_prices.append({'price': match, 'value': value})

            if found_prices:
                found_prices.sort(key=lambda x: x['value'], reverse=True)
                valuation = found_prices[0]['price']
                logger.info(f"    ✓ Valuation: {valuation}")
                return valuation

            return None

        except Exception as e:
            logger.error(f"    ✗ Error: {str(e)[:100]}")
            return None
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass

    def process_cars(self, pistonheads_url=None, autotrader_url=None, postcode="M32 9AU", max_cars_per_site=None):
        """Main process"""
        start_time = datetime.now()

        logger.info("\n" + "=" * 70)
        logger.info("MULTI-PLATFORM CAR VALUATION BOT")
        logger.info("=" * 70 + "\n")

        all_cars = []

        if pistonheads_url:
            ph_cars = self.scrape_pistonheads(pistonheads_url)
            if max_cars_per_site and ph_cars:
                ph_cars = ph_cars[:max_cars_per_site]
            all_cars.extend(ph_cars)

        if autotrader_url:
            at_cars = self.scrape_autotrader(autotrader_url, max_cars=max_cars_per_site)
            all_cars.extend(at_cars)

        if not all_cars:
            logger.error("No cars scraped. Exiting.")
            return []

        logger.info(f"✓ Total scraped: {len(all_cars)} cars\n")

        logger.info("=" * 70)
        logger.info("DETECTING PLATES AND VALUATIONS")
        logger.info("=" * 70 + "\n")

        for idx, car in enumerate(all_cars, 1):
            logger.info(f"[{idx}/{len(all_cars)}] [{car['source']}] {car['title'][:45]}")
            logger.info(f"  Price: {car.get('price', 'N/A')}")

            plate = None
            for img_url in car.get('images', [])[:4]:
                logger.info(f"  Checking image...")
                plate = self.detect_license_plate(img_url)
                if plate:
                    logger.info(f"  ✓ Plate: {plate}")
                    break
                time.sleep(0.5)

            car['detected_plate'] = plate if plate else "Not detected"

            if plate and car.get('mileage'):
                try:
                    mileage = int(car['mileage'])
                    valuation = self.get_valuation(plate, mileage, postcode)
                    car['webuyanycar_valuation'] = valuation if valuation else "Failed"

                    if valuation:
                        logger.info(f"  ✓ Valuation: {valuation}\n")
                    else:
                        logger.info(f"  ✗ Valuation failed\n")
                except Exception as e:
                    logger.error(f"  ✗ Error: {str(e)[:100]}\n")
                    car['webuyanycar_valuation'] = "Error"
            else:
                car['webuyanycar_valuation'] = "No plate/mileage"
                logger.info(f"  ✗ Skipped\n")

            self.results.append(car)
            time.sleep(1)

        self.save_results()

        elapsed = datetime.now() - start_time
        logger.info("\n" + "=" * 70)
        logger.info(f"✓ COMPLETED IN {elapsed.total_seconds():.1f} SECONDS")
        logger.info("=" * 70)

        return self.results

    def save_results(self, filename='car_valuations_results.json'):
        """Save results to JSON"""
        output = {
            'timestamp': datetime.now().isoformat(),
            'total_cars': len(self.results),
            'sources': {},
            'plates_detected': sum(1 for c in self.results if c.get('detected_plate') != "Not detected"),
            'valuations_obtained': sum(1 for c in self.results if c.get('webuyanycar_valuation')
                                       not in ["Failed", "Error", "No plate/mileage", "No plate or mileage"]),
            'cars': self.results
        }

        for car in self.results:
            source = car.get('source', 'Unknown')
            output['sources'][source] = output['sources'].get(source, 0) + 1

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        logger.info(f"\n✓ Results saved to {filename}")

        logger.info("\n" + "=" * 70)
        logger.info("SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Total cars: {output['total_cars']}")
        for source, count in output['sources'].items():
            logger.info(f"  - {source}: {count}")
        logger.info(f"Plates detected: {output['plates_detected']}")
        logger.info(f"Valuations obtained: {output['valuations_obtained']}")

    def save_to_csv(self, filename='car_valuations_results.csv'):
        """Save results to CSV"""
        if not self.results:
            logger.info("No results to save to CSV")
            return

        headers = ['source', 'title', 'price', 'year', 'mileage', 'transmission',
                   'fuelType', 'link', 'detected_plate', 'webuyanycar_valuation']

        max_images = max(len(car.get('images', [])) for car in self.results) if self.results else 0
        for i in range(1, min(max_images + 1, 11)):
            headers.append(f'image_{i}')

        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers, extrasaction='ignore')
            writer.writeheader()

            for car in self.results:
                row = car.copy()
                images = row.pop('images', [])
                for i, img in enumerate(images[:10], 1):
                    row[f'image_{i}'] = img
                writer.writerow(row)

        logger.info(f"✓ Results also saved to {filename}")


def main():
    """Main execution"""

    # Configuration
    PISTONHEADS_URL = 'https://www.pistonheads.com/buy/search?distance=60&mileage=100000&mileage=175000&postcode=M32%209AU&price=8000&price=15000&sort-order=Date&year=2010&year=2022'
    AUTOTRADER_URL = 'https://www.autotrader.co.uk/car-search?advertising-location=at_cars&channel=cars&homeDeliveryAdverts=include&maximum-mileage=150000&minimum-mileage=100000&postcode=M329AU&radius=50&sort=relevance&year-to=2026'
    POSTCODE = "M32 9AU"
    MAX_CARS_PER_SITE = 15
    HEADLESS = True  # Change to True for production/server deployment

    # Email configuration - FROM ENVIRONMENT VARIABLES
    SENDER_EMAIL = os.getenv('SENDER_EMAIL', 'your-email@gmail.com')
    SENDER_PASSWORD = os.getenv('SENDER_PASSWORD', 'xxxx xxxx xxxx xxxx')
    RECIPIENT_EMAIL = os.getenv('RECIPIENT_EMAIL', 'your-email@gmail.com')  # Change this

    # Initialize bot and email
    bot = CarValuationBot(headless=HEADLESS)
    email_reporter = EmailReporter(SENDER_EMAIL, SENDER_PASSWORD)

    # Run bot and send email
    logger.info("\n🚗 RUNNING BOT AND SENDING EMAIL\n")
    results = bot.process_cars(
        pistonheads_url=PISTONHEADS_URL,
        autotrader_url=AUTOTRADER_URL,
        postcode=POSTCODE,
        max_cars_per_site=MAX_CARS_PER_SITE
    )
    bot.save_to_csv()
    email_reporter.send_report(RECIPIENT_EMAIL, results)

    logger.info("\n✓ Bot execution completed!")


if __name__ == "__main__":
    main()