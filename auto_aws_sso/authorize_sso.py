import os
from pathlib import Path

from selenium import webdriver
from selenium.common import TimeoutException
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

    if os.getenv("CUSTOM_USER_AGENT"):
        user_agent = os.getenv("CUSTOM_USER_AGENT", "")
        options.add_argument(f"user-agent={user_agent}")

    return webdriver.Chrome(options=options)


def authorize_sso(url: str, *, headless: bool) -> None:
    print(f"Running in headless - {headless}")
    driver = build_driver(headless=headless)
    page_load_timeout = 10 if headless else 500
    url_with_code = f"{url}"
    driver.get(url_with_code)

    try:
        print("Waiting for the page to load")

        # Try waiting for the allow-access-button but only briefly (like 5 seconds)
        try:
            login_button = WebDriverWait(driver, 5).until(
                ec.element_to_be_clickable((By.XPATH, "//button[@data-testid='allow-access-button']")),
            )
            print("Clicking on the allow button")
            login_button.click()
        except TimeoutException:
            # If the button never shows up, just print a note and move on
            print("Allow button not found, assuming page will load directly")

        print("Waiting for the confirmation page to load")
        # Wait for the confirmation text to appear on the page (longer timeout here)
        WebDriverWait(driver, page_load_timeout).until(
            ec.text_to_be_present_in_element((By.TAG_NAME, "body"), "Request approved"),
        )
        print("Done")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        driver.quit()
