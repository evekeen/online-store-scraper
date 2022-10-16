from selenium.webdriver.chrome.service import Service
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
import os
import re
import urllib.request
import time
import shutil
import socket

urls = [
    "https://www.rei.com/c/womens-swimwear",
    "https://www.rei.com/c/womens-yoga-clothing",
    "https://www.rei.com/c/womens-workout-clothing",
    "https://www.rei.com/c/mens-workout-clothing",
    "https://www.rei.com/c/mens-yoga-clothing"
]


class Scraper:
    driver: webdriver.Chrome = None
    wait: WebDriverWait = None
    wait_short: WebDriverWait = None
    trial = 1

    def scrape(self):
        seen_products = set()
        for url in urls:
            self.driver.get(url)
            name = url.rpartition('/')[-1]
            print('----- Loading image from page: {}\n'.format(name))
            if not os.path.exists(name):
                os.mkdir(name)

            page_buttons = self.driver.find_elements(By.CSS_SELECTOR, "nav > a")
            last_page_url = page_buttons[-2].get_attribute('href')
            matches = re.search(r"\?page=(\d+)", last_page_url)
            page_count = int(matches.group(1))

            start_page = 1

            for page in range(start_page, page_count):
                print('page #{}/{}'.format(page, page_count))
                page_url = '{}?page={}'.format(url, page)
                self.driver.get(page_url)
                try:
                    self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '#search-results > ul > li > a')))
                except:
                    print('No product urls found')
                    continue

                products = self.driver.find_elements(By.CSS_SELECTOR, "#search-results > ul > li > a")
                print('products on page', len(products))
                product_urls = list(map(lambda p: p.get_attribute('href'), products))

                for product_url in product_urls:
                    matches = re.search(r"/product/(\d+/.*)", product_url)
                    if not matches:
                        print('ERROR: Could not parse the product page', product_url)
                        continue
                    product_id = matches.group(1).replace('/', '-')
                    if product_id in seen_products:
                        continue
                    seen_products.add(product_id)

                    self.load_product(product_url, name, product_id)
                # sleep one minute after each page - to avoid being blocked
                time.sleep(1)

    def load_product(self, product_url, name, product_id):
        print('product url {}\n'.format(product_url))

        product_path = os.path.join(name, product_id)
        if os.path.exists(product_path):
            print('product already downloaded')
            return

        tmp_product_path = os.path.join(name, 'tmp-{}'.format(product_id))
        if os.path.exists(tmp_product_path):
            shutil.rmtree(tmp_product_path)
        os.mkdir(tmp_product_path)

        self.driver.get(product_url)

        if self.driver.find_elements(By.CSS_SELECTOR, '.ui-slideshow-slide__image-wrapper'):
            product_loaded = self.load_slideshow_product(tmp_product_path)
        else:
            product_loaded = self.load_carousel_product(tmp_product_path)
        if product_loaded:
            os.mkdir(product_path)
            shutil.move(tmp_product_path, product_path, copy_function=shutil.copytree)
        else:
            print('retrying #{} after delay...'.format(self.trial))
            self.driver.quit()
            self.init_driver()
            delay = min(540, 180 * self.trial)
            time.sleep(delay)
            self.trial += 1
            self.load_product(product_url, name, product_id)

    def load_carousel_product(self, product_path):
        try:
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '#container')))
        except:
            print('bad page state detected')
            return False
        try:
            self.wait_short.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.buy-box__purchase-form fieldset button')))
        except:
            print('No colors found')
            return False
        color_buttons = self.driver.find_elements(By.CSS_SELECTOR, '.buy-box__purchase-form fieldset button')

        print('carousel color options:', len(color_buttons))
        for button in color_buttons:
            color_name = button.get_attribute('data-color')
            if not color_name:
                continue
            color_name = re.sub(r'[\s|/]', '-', color_name).lower()

            variant_path = os.path.join(product_path, color_name)
            if not os.path.exists(variant_path):
                os.mkdir(variant_path)

            button.click()
            try:
                self.wait_short.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '#apparel-media-image-container .media-center-carousel__image-button > img')))
            except:
                print('No variants found')
                continue
            images = self.driver.find_elements(By.CSS_SELECTOR, '#apparel-media-image-container .media-center-carousel__image-button > img')
            print('> {} carousel images: {}'.format(color_name, len(images)))
            i = 1
            for image in images:
                src = image.get_attribute('src')
                src = src.replace('https://www.rei.com', '')
                matches = re.search(r"(/media/(.*)\?size=).*", src)
                if matches:
                    if not self.download_image(variant_path, i, matches):
                        return False
                    i += 1
                else:
                    print('ERROR: cannot parse url', src)
        return True

    def load_slideshow_product(self, product_path):
        try:
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '#container')))
        except:
            print('bad page state detected')
            return False
        try:
            self.wait_short.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'ui-slideshow-navigation .ui-slideshow-control__image')))
        except:
            print('No variants found')
            return True
        images = self.driver.find_elements(By.CSS_SELECTOR, 'ui-slideshow-navigation .ui-slideshow-control__image')
        print('> slideshow images: {}'.format(len(images)))
        i = 1
        for image in images:
            src = image.get_attribute('src')
            src = src.replace('https://www.rei.com', '')
            matches = re.search(r"(/media/(.*)(\?size=.*)?)", src)
            if matches:
                alt = image.get_attribute('alt')
                color_name = alt.rpartition(' ')[-1]
                if not color_name:
                    continue
                color_name = re.sub(r'[\s|/]', '-', color_name).lower()

                variant_path = os.path.join(product_path, color_name)
                if not os.path.exists(variant_path):
                    os.mkdir(variant_path)

                if not self.download_image(variant_path, i, matches):
                    return False
                i += 1
            else:
                print('ERROR: cannot parse url', src)
        return i > 1

    def download_image(self, variant_path, i, matches):
        image_base = matches.group(1)
        image_id = matches.group(2)
        image_url = image_base + '576x768'
        print(image_id)
        image_path = os.path.join(variant_path, '{}-{}.jpg'.format(i, image_id))
        if not os.path.exists(image_path):
            try:
                urllib.request.urlretrieve("https://www.rei.com" + image_url, image_path)
            except:
                print('retrying the download...')
                try:
                    urllib.request.urlretrieve("https://www.rei.com" + image_url, image_path)
                except:
                    return False
        return True

    def init_driver(self):
        service = Service(executable_path='/Users/ivkin/bin/chromedriver')

        options = Options()
        user_agent = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/33.0.1750.517 Safari/537.36'
        options.add_argument('user-agent={0}'.format(user_agent))
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        self.driver = webdriver.Chrome(options=options, service=service)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                                                                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                                                                                  'Chrome/85.0.4183.102 Safari/537.36'})

        self.wait = WebDriverWait(self.driver, 30)
        self.wait_short = WebDriverWait(self.driver, 5)


socket.setdefaulttimeout(30)
scraper = Scraper()
try:
    scraper.init_driver()
    scraper.scrape()
finally:
    scraper.driver.quit()
