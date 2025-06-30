import os
import json
import time
import logging
import re

import gspread
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from google.oauth2.service_account import Credentials

# ───── Logging ─────
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ───── Config ─────
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")
GGL_CREDENTIALS = os.getenv("GGL_CREDENTIALS")
SHEET_ID = os.getenv("SHEET_ID")
SHEET_NAME = "FUNCIONARIOS"
GOOGLE_SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]

if not all([USERNAME, PASSWORD, GGL_CREDENTIALS, SHEET_ID]):
    raise ValueError("One or more required environment variables are missing.")

# ───── Chrome Setup ─────
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
prefs = {"download.prompt_for_download": False}
chrome_options.add_experimental_option("prefs", prefs)
driver = webdriver.Chrome(options=chrome_options)

# ───── Helpers ─────
def authorize_gspread():
    creds_dict = json.loads(GGL_CREDENTIALS)
    creds = Credentials.from_service_account_info(creds_dict, scopes=GOOGLE_SCOPE)
    return gspread.authorize(creds)

def get_cod_nome_mapping():
    client = authorize_gspread()
    sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
    codes = sheet.col_values(3)
    names = sheet.col_values(5)
    return {str(c): n for c, n in zip(codes, names)}

def extract_numeric(cell_text):
    if cell_text.isdigit():
        return cell_text
    match = re.search(r"Atendente:(\d+)", cell_text)
    return match.group(1) if match else None

def clear_and_type(elem, value):
    elem.send_keys(Keys.CONTROL + "a")
    elem.send_keys(Keys.DELETE)
    elem.send_keys(value)

def handle_popup(driver, numeric_code, mapping):
    try:
        popup = WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "div.popover.fade.top.in.editable-container"))
        )
        input_field = WebDriverWait(popup, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input.form-control.input-sm"))
        )

        new_value = "E-COMMERCE" if numeric_code == "548" else mapping.get(numeric_code)
        if not new_value:
            logging.info(f"No mapping for code {numeric_code}. Skipping.")
            cancel_button = WebDriverWait(popup, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn.btn-default.btn-sm.editable-cancel"))
            )
            cancel_button.click()
            return

        clear_and_type(input_field, new_value)
        logging.info(f"Updated {numeric_code} to {new_value}")

        save_button = WebDriverWait(popup, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn.btn-primary.btn-sm.editable-submit"))
        )
        save_button.click()

        WebDriverWait(driver, 5).until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, "div.popover.fade.top.in.editable-container"))
        )
    except Exception as e:
        logging.error(f"Popup error for code {numeric_code}: {e}")
        try:
            driver.find_element(By.CSS_SELECTOR, "button.editable-cancel").click()
        except:
            pass

def process_table(driver, mapping):
    try:
        table = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table.table-bordered"))
        )
        rows = table.find_elements(By.CSS_SELECTOR, "tr:not(.tablesorter-headerRow)")
        for idx, row in enumerate(rows, 1):
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) < 5:
                continue

            cell = cells[4]
            code = extract_numeric(cell.text.strip())
            if code:
                logging.info(f"Row {idx}: Found numeric code '{code}'")
                for selector in ["a", "button", "input[type='button']", "input[type='submit']", "div[onclick]"]:
                    try:
                        clickable = cell.find_element(By.CSS_SELECTOR, selector)
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'})", clickable)
                        WebDriverWait(driver, 2).until(EC.element_to_be_clickable(clickable))
                        clickable.click()
                        handle_popup(driver, code, mapping)
                        time.sleep(1)
                        break
                    except:
                        continue
    except Exception as e:
        logging.error(f"Error processing table: {e}")

def next_page(driver):
    try:
        next_li = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "li.page-item.next"))
        )
        if "disabled" in next_li.get_attribute("class"):
            return False
        next_button = next_li.find_element(By.TAG_NAME, "a")
        next_button.click()
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table.table-bordered"))
        )
        time.sleep(2)
        return True
    except:
        return False

# ───── Main ─────
def main():
    try:
        logging.info("Opening the URL and logging in")
        driver.get("https://adm.bunker.mk/action.do?mod=mOCN6D58wTE%C2%A2&id=Y1RMmN89MCY%C2%A2")
        mapping = get_cod_nome_mapping()

        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "email"))).send_keys(USERNAME)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "password"))).send_keys(PASSWORD)
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "/html/body/div/div/div[2]/form/fieldset/div[6]/div[2]/input"))).click()

        WebDriverWait(driver, 10).until(lambda d: d.execute_script("return document.readyState") == "complete")
        time.sleep(2)

        page = 1
        while True:
            logging.info(f"Processing page {page}")
            process_table(driver, mapping)
            if not next_page(driver):
                break
            page += 1
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
