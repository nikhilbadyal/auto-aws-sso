import os
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait

from auto_aws_sso.constant import project_selenium_dir


def build_driver(*, headless: bool) -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    if os.getenv("CHROME_BINARY"):
        options.binary_location = os.getenv("CHROME_BINARY", "")
    _user_data_dir = Path.home() / project_selenium_dir
    options.add_argument(f"user-data-dir={_user_data_dir}")
    if headless:
        options.add_argument("headless")
    return webdriver.Chrome(options=options)


def authorize_sso(url: str, code: str, *, headless: bool) -> None:
    print(f"Running in headless - {headless}")
    driver = build_driver(headless=headless)
    page_load_timeout = 10 if headless else 500
    url_with_code = f"{url}?user_code={code}"
    driver.get(url_with_code)

    try:
        print("Waiting for the page to load")
        submit_button = WebDriverWait(driver, page_load_timeout).until(
            ec.element_to_be_clickable((By.ID, "cli_verification_btn")),
        )
        print("Clicking on the verification button")
        submit_button.click()
        submit_button.click()
        print("Waiting for the allow page to load")

        login_button = WebDriverWait(driver, page_load_timeout).until(
            ec.element_to_be_clickable((By.XPATH, "//button[@data-testid='allow-access-button']")),
        )
        print("Clicking on the allow button")
        login_button.click()
        print("Waiting for the confirmation page to load")

        WebDriverWait(driver, page_load_timeout).until(
            ec.text_to_be_present_in_element((By.TAG_NAME, "body"), "You can close this window."),
        )
        print("Done")

    except Exception as e:
        print("An error occurred: %s", str(e))
    finally:
        driver.quit()
