"""
Complete Car Valuation Bot - Railway Production Ready
Scrapes PistonHeads + AutoTrader -> Detects plates -> Gets valuations -> Sends email report
Optimized for headless Chrome deployment
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


def get_chrome_options():
    """Get Chrome options for headless deployment"""
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    
    # Additional optimizations
    chrome_options.add_argument('--disable-software-rasterizer')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # User agent
    chrome_options.add_argument(
        'user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    
    # Window size and logging
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--log-level=3')
    
    # Memory optimization for cloud
    chrome_options.add_argument('--single-process')
    
    return chrome_options


def get_chrome_driver():
    """Get Chrome driver with proper configuration for Railway/cloud deployment"""
    chrome_options = get_chrome_options()
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        logger.info("✓ Chrome driver initialized")
        return driver
    except Exception as e:
        logger.error(f"Failed to initialize Chrome: {e}")
        raise


class EmailReporter:
    """Handle email sending"""

    def __init__(self, sender_email, sender_password, smtp_server='smtp.gmail.com', smtp_port=587):
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

            msg = MIMEMultipart()
            msg['From'] = self.sender_email
            msg['To'] = recipient_email
            msg['Subject'] = f"🚗 Car Valuation Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}"

            html_body = self._generate_html_report(results)
            msg.attach(MIMEText(html_body, 'html'))

            # Attach files
            for filename in [json_file, csv_file]:
                try:
                    with open(filename, 'rb') as attachment:
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(attachment.read())
                        encoders.encode_base64(part)
                        part.add_header('Content-Disposition', f'attachment; filename= {filename}')
                        msg.attach(part)
                        logger.info(f"✓ Attached {filename}")
                except FileNotFoundError:
                    logger.warning(f"⚠ {filename} not found")

            logger.info(f"Sending to {recipient_email}...")
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)

            logger.info(f"✓ Email sent successfully")
            logger.info("=" * 70)
            return True

        except Exception as e:
            logger.error(f"✗ Error sending email: {e}")
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
            link_html = f'<a href="{link}" target="_blank">View</a>' if link and link != '#' else 'N/A'
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
                .header {{ background-color: #2c3e50; color: white; padding: 20px; }}
                .summary {{ background-color: #ecf0f1; padding: 15px; margin: 20px 0; }}
                .stats {{ display: flex; gap: 20px; margin: 15px 0; }}
                .stat-box {{ background-color: #3498db; color: white; padding: 15px; flex: 1; text-align: center; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th, td {{ border: 1px solid #bdc3c7; padding: 10px; text-align: left; }}
                th {{ background-color: #34495e; color: white; }}
                tr:nth-child(even) {{ background-color: #ecf0f1; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🚗 Car Valuation Report</h1>
                <p>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            <div class="summary">
                <h2>Summary</h2>
                <div class="stats">
                    <div class="stat-box"><h3>{total}</h3><p>Total Cars</p></div>
                    <div class="stat-box"><h3>{plates_detected}</h3><p>Plates Detected</p></div>
                    <div class="stat-box"><h3>{valuations}</h3><p>Valuations</p></div>
                </div>
                <h3>By Source</h3>
                <ul>{source_html}</ul>
            </div>
            <h2>Top Results</h2>
            <table>
                <tr>
                    <th>#</th><th>Source</th><th>Title</th><th>Price</th>
                    <th>Mileage</th><th>Plate</th><th>Valuation</th><th>Link</th>
                </tr>
                {cars_html}
            </table>
        </body>
        </html>
        """
        return html


class CarValuationBot:
    def __init__(self, ocr_api_key='K87899142388957'):
        self.ocr_api_key = ocr_api_key
        self.results = []

    def extract_images_from_detail_page(self, driver, url, max_images=10):
        """Extract images from AutoTrader detail page"""
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
                        if (src and src.startswith('http') and
                                'placeholder' not in src.lower() and
                                'logo' not in src.lower() and
                                'icon' not in src.lower()):
                            images.append(src)
                            break
                    except:
                        continue
                        
                if len(images) >= max_images:
                    break
                    
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
        """Scrape AutoTrader with headless Chrome"""
        logger.info("=" * 70)
        logger.info("SCRAPING CARS FROM AUTOTRADER")
        logger.info("=" * 70)

        driver = None
        cars = []
        seen_titles = set()

        try:
            driver = get_chrome_driver()

            logger.info("Loading AutoTrader page...")
            driver.get(url)
            time.sleep(10)

            # Accept cookies
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
            for i in range(15):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)

            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            logger.info("\nExtracting car data...\n")

            all_selectors = [
                "li[data-advert-id]",
                "li[data-testid='trader-seller-listing']",
                "article[data-testid='trader-seller-listing']",
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
                articles = driver.find_elements(By.TAG_NAME, "article")
                potential_listings = [a for a in articles if '£' in a.text and 'miles' in a.text.lower()]
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

                    car = {'source': 'AutoTrader'}

                    # Extract title
                    title_text = None
                    title_selectors = ["h3", "h2", "a[href*='/car-details']"]

                    for selector in title_selectors:
                        try:
                            title_elem = listing.find_element(By.CSS_SELECTOR, selector)
                            title_text = title_elem.text.strip()
                            if title_text and len(title_text) > 10:
                                break
                        except:
                            continue

                    if title_text:
                        car['title'] = title_text
                    else:
                        continue

                    # Extract price
                    price_match = re.search(r'£([\d,]+)', listing_text)
                    if price_match:
                        car['price'] = f"£{price_match.group(1)}"

                    # Extract link
                    try:
                        link_elem = listing.find_element(By.CSS_SELECTOR, "a[href*='/car-details']")
                        car['link'] = link_elem.get_attribute('href')
                    except:
                        car['link'] = None

                    # Extract specs
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

                    # Extract images
                    if car.get('link'):
                        logger.info(f"  → Fetching images: {car['title'][:50]}")
                        car['images'] = self.extract_images_from_detail_page(driver, car['link'], max_images=4)
                        logger.info(f"    ✓ Found {len(car['images'])} images")
                    else:
                        car['images'] = []

                    if car.get('title') and car.get('price'):
                        unique_key = f"{car['title'].lower().strip()}_{car.get('price', '')}"
                        if unique_key not in seen_titles:
                            seen_titles.add(unique_key)
                            cars.append(car)
                            logger.info(f"✓ {len(cars)}. {car['title'][:55]} - {car['price']}")

                except Exception as e:
                    logger.debug(f"Error parsing listing {idx + 1}: {str(e)[:50]}")
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
        """Scrape PistonHeads"""
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
                    car['price'] = price_elem.get_text(strip=True) if hasattr(price_elem,
                                                                               'get_text') else str(price_elem).strip()

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

                if car.get('title') and car.get('price') and len(car.get('images', [])) >= min_images:
                    title_key = car['title'].lower().strip()
                    if title_key not in seen_titles:
                        seen_titles.add(title_key)
                        cars.append(car)
                        logger.info(f"✓ {len(cars)}. {car['title'][:50]} ({len(car['images'])} images)")

            except Exception as e:
                logger.debug(f"Error parsing listing: {e}")
                continue

        logger.info(f"\n✓ Successfully scraped {len(cars)} cars from PistonHeads\n")
        return cars

    def detect_license_plate(self, image_url, max_retries=3):
        """Detect license plate using OCR"""
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

                patterns = [
                    r'\b[A-Z]{2}\d{2}\s*[A-Z]{3}\b',
                    r'\b[A-Z]{2}[-]?\d{2}\s*[-]?[A-Z]{3}\b',
                    r'\b[A-Z]\d{1,3}\s*[A-Z]{3}\b',
                ]

                for pattern in patterns:
                    matches = re.findall(pattern, text)
                    if matches:
                        return matches[0].replace(' ', '').replace('-', '')

                return None

            except Exception as e:
                logger.debug(f"OCR attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)
                return None

        return None

    def get_valuation(self, registration, mileage, postcode="M32 9AU"):
        """Get valuation from Webuyanycar with headless Chrome"""
        logger.info(f"  Getting valuation for {registration}...")

        driver = None

        try:
            driver = get_chrome_driver()
            driver.set_page_load_timeout(30)
            wait = WebDriverWait(driver, 20)

            logger.info("    Loading homepage...")
            driver.get("https://www.webuyanycar.com/")
            time.sleep(4)

            # Handle cookies
            try:
                cookie_btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH,
                                                "//button[contains(text(), 'Allow all cookies')]"))
                )
                cookie_btn.click()
                time.sleep(1)
                logger.info("    ✓ Cookies accepted")
            except:
                logger.info("    ⚠ No cookie banner")

            logger.info("    Entering registration...")
            try:
                reg_input = wait.until(EC.presence_of_element_located((By.ID, "vehicleReg")))
            except:
                reg_input = wait.until(EC.presence_of_element_located((By.NAME, "vehicleReg")))

            reg_input.clear()
            reg_input.send_keys(registration)
            time.sleep(0.5)

            logger.info("    Entering mileage...")
            try:
                mileage_input = driver.find_element(By.NAME, "Mileage")
            except:
                mileage_input = driver.find_element(By.ID, "Mileage")

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
                logger.error("    ✗ Timeout")
                return None

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
            except:
                pass

            try:
                postcode_input = driver.find_element(By.XPATH,
                                                     "//input[contains(@placeholder, 'postcode')]")
                driver.execute_script("arguments[0].scrollIntoView(true);", postcode_input)
                time.sleep(0.3)
                postcode_input.click()
                postcode_input.clear()
                postcode_input.send_keys(postcode)
                logger.info(f"    ✓ Postcode: {postcode}")
                time.sleep(0.5)
            except:
                pass

            logger.info("    Looking for submit button...")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            valuation_btn = None
            buttons = driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                if 'Get my valuation' in btn.text and btn.is_displayed():
                    valuation_btn = btn
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
                    logger.info(f"    ✓ Plate detected: {plate}")
                    break

            car['detected_plate'] = plate if plate else "Not detected"

            if plate and car.get('mileage'):
                try:
                    mileage = int(re.sub(r'[^\d]', '', car['mileage']))
                    valuation = self.get_valuation(plate, mileage, postcode)
                    car['webuyanycar_valuation'] = valuation if valuation else "Failed"
                except:
                    car['webuyanycar_valuation'] = "Error"
            else:
                car['webuyanycar_valuation'] = "No plate or mileage"

            logger.info("")

        self.results = all_cars

        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_file = f'car_valuations_{timestamp}.json'
        csv_file = f'car_valuations_{timestamp}.csv'

        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(all_cars, f, indent=2, ensure_ascii=False)

        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            if all_cars:
                fieldnames = ['source', 'title', 'price', 'mileage', 'year', 'transmission',
                              'fuelType', 'detected_plate', 'webuyanycar_valuation', 'link']
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(all_cars)

        logger.info("=" * 70)
        logger.info("SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Total cars processed: {len(all_cars)}")
        logger.info(f"Plates detected: {sum(1 for c in all_cars if c.get('detected_plate') != 'Not detected')}")
        logger.info(f"Valuations obtained: {sum(1 for c in all_cars if c.get('webuyanycar_valuation') not in ['Failed', 'Error', 'No plate or mileage'])}")
        logger.info(f"Time taken: {datetime.now() - start_time}")
        logger.info(f"Results saved: {json_file}, {csv_file}")
        logger.info("=" * 70)

        return all_cars


def main():
    """Main entry point"""
    # Configuration
    PISTONHEADS_URL = "https://www.pistonheads.com/buy/listing/porsche"
    AUTOTRADER_URL = "https://www.autotrader.co.uk/car-search?make=Porsche"
    MAX_CARS_PER_SITE = 5
    POSTCODE = "M32 9AU"

    # Email configuration from environment variables
    SENDER_EMAIL = os.getenv('SENDER_EMAIL')
    SENDER_PASSWORD = os.getenv('SENDER_PASSWORD')
    RECIPIENT_EMAIL = os.getenv('RECIPIENT_EMAIL')

    # Initialize bot
    bot = CarValuationBot()

    # Process cars
    results = bot.process_cars(
        pistonheads_url=PISTONHEADS_URL,
        autotrader_url=AUTOTRADER_URL,
        postcode=POSTCODE,
        max_cars_per_site=MAX_CARS_PER_SITE
    )

    # Send email if configured
    if SENDER_EMAIL and SENDER_PASSWORD and RECIPIENT_EMAIL and results:
        reporter = EmailReporter(SENDER_EMAIL, SENDER_PASSWORD)
        reporter.send_report(
            RECIPIENT_EMAIL,
            results,
            json_file=f'car_valuations_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json',
            csv_file=f'car_valuations_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )


if __name__ == "__main__":
    main()
