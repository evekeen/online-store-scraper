from selenium.webdriver.chrome.service import Service
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver import ActionChains
import os
import re
import urllib.request
import time
import shutil

urls = [
    "https://www.rei.com/c/mens-tops",
    "https://www.rei.com/c/mens-bottoms",
    "https://www.rei.com/c/mens-swimwear",
    "https://www.rei.com/c/womens-jackets",
    "https://www.rei.com/c/womens-tops",
    "https://www.rei.com/c/womens-bottoms",
    "https://www.rei.com/c/womens-skirts-and-dresses",
    "https://www.rei.com/c/womens-swimwear",
    "https://www.rei.com/c/womens-yoga-clothing",
    "https://www.rei.com/c/womens-workout-clothing",
    "https://www.rei.com/c/mens-workout-clothing",
    "https://www.rei.com/c/mens-yoga-clothing"
]


def scrape():
    seen_products = set()
    for url in urls:
        driver.get(url)
        name = url.rpartition('/')[-1]
        print('----- Loading image from page: {}\n'.format(name))
        if not os.path.exists(name):
            os.mkdir(name)

        page_buttons = driver.find_elements(by=By.CSS_SELECTOR, value="nav > a")
        last_page_url = page_buttons[-2].get_attribute('href')
        matches = re.search(r"\?page=(\d+)", last_page_url)
        page_count = int(matches.group(1))

        start_page = 1

        for page in range(start_page, page_count):
            print('page #{}/{}'.format(page, page_count))
            page_url = '{}?page={}'.format(url, page)
            driver.get(page_url)
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '#search-results > ul > li > a')))
            except:
                print('No product urls found')
                continue

            products = driver.find_elements(By.CSS_SELECTOR, "#search-results > ul > li > a")
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

                load_product(product_url, name, product_id, 1)
            # sleep one minute after each page - to avoid being blocked
            time.sleep(60)


def load_product(product_url, name, product_id, trial):
    print('product url {}\n'.format(product_url))

    product_path = os.path.join(name, product_id)
    if os.path.exists(product_path):
        print('product already downloaded')
        return

    tmp_product_path = os.path.join(name, 'tmp-{}'.format(product_id))
    shutil.rmtree(tmp_product_path)
    os.mkdir(tmp_product_path)

    driver.get(product_url)

    if driver.find_elements(By.CSS_SELECTOR, '.ui-slideshow-slide__image-wrapper'):
        product_loaded = load_slideshow_product(tmp_product_path)
    else:
        product_loaded = load_carousel_product(tmp_product_path)
    if product_loaded:
        os.mkdir(product_path)
        shutil.move(tmp_product_path, product_path, copy_function=shutil.copytree)
    else:
        print('retrying #{} after delay...'.format(trial))
        time.sleep(120 * trial)
        load_product(product_url, name, product_id, trial + 1)


def load_carousel_product(product_path):
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.buy-box__purchase-form fieldset button')))
    except:
        print('No colors found')
        return False
    color_buttons = driver.find_elements(By.CSS_SELECTOR, '.buy-box__purchase-form fieldset button')

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
            wait_short.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '#apparel-media-image-container .media-center-carousel__image-button > img')))
        except:
            print('No variants found')
            continue
        images = driver.find_elements(By.CSS_SELECTOR, '#apparel-media-image-container .media-center-carousel__image-button > img')
        print('> {} carousel images: {}'.format(color_name, len(images)))
        i = 1
        for image in images:
            src = image.get_attribute('src')
            src = src.replace('https://www.rei.com', '')
            matches = re.search(r"(/media/(.*)\?size=).*", src)
            if matches:
                download_image(variant_path, i, matches)
                i += 1
            else:
                print('ERROR: cannot parse url', src)
    return True


def load_slideshow_product(product_path):
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'ui-slideshow-navigation .ui-slideshow-control__image')))
    except:
        print('No variants found')
        return False
    images = driver.find_elements(By.CSS_SELECTOR, 'ui-slideshow-navigation .ui-slideshow-control__image')
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

            download_image(variant_path, i, matches)
            i += 1
        else:
            print('ERROR: cannot parse url', src)
    return i > 1


def download_image(variant_path, i, matches):
    image_base = matches.group(1)
    image_id = matches.group(2)
    image_url = image_base + '576x768'
    print(image_id)
    image_path = os.path.join(variant_path, '{}-{}.jpg'.format(i, image_id))
    if not os.path.exists(image_path):
        urllib.request.urlretrieve("https://www.rei.com" + image_url, image_path)


service = Service(executable_path='/Users/ivkin/bin/chromedriver')

options = Options()
user_agent = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/33.0.1750.517 Safari/537.36'
options.add_argument('user-agent={0}'.format(user_agent))
options.add_argument('--disable-blink-features=AutomationControlled')
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option('useAutomationExtension', False)
driver = webdriver.Chrome(options=options, service=service)
driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                                                     'AppleWebKit/537.36 (KHTML, like Gecko) '
                                                                     'Chrome/85.0.4183.102 Safari/537.36'})

wait = WebDriverWait(driver, 30)
wait_short = WebDriverWait(driver, 5)
action = ActionChains(driver)

try:
    scrape()
finally:
    driver.quit()
