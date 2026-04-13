"""
Redeems winning Polymarket positions via the portfolio web UI using Selenium.

Launches headless Chrome automatically, claims all available positions,
then shuts Chrome down. Repeats every 5 minutes.

Usage:
    poetry run python redeem.py
"""

import subprocess
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.config import getLogger

logger = getLogger(__name__)

PORTFOLIO_URL = "https://polymarket.com/portfolio"
DEBUG_PORT = "localhost:9222"
CHROME_PROFILE = str(Path.home() / ".chrome-polymarket")
WAIT_TIMEOUT = 20
CHROME_STARTUP_WAIT = 3  # seconds for headless Chrome to be ready
POST_CLAIM_WAIT = 10  # seconds after closing notification before next claim
SLEEP_BETWEEN_RUNS = 300  # 5 minutes

# XPath selectors derived from inspecting the portfolio page
_CLAIM_BTN = "//button[normalize-space(.)='Claim']"
_CONFIRM_BTN = "//button[starts-with(normalize-space(.), 'Claim $')]"
_CLOSE_BTN = "//button[@aria-label='Close']"


def launch_chrome() -> subprocess.Popen:
    return subprocess.Popen(
        [
            "google-chrome",
            "--remote-debugging-port=9222",
            f"--user-data-dir={CHROME_PROFILE}",
            "--headless=new",
            # "--no-sandbox",
            # "--disable-dev-shm-usage",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def make_driver() -> webdriver.Chrome:
    opts = Options()
    opts.debugger_address = DEBUG_PORT
    return webdriver.Chrome(options=opts)


def claim_all(driver: webdriver.Chrome) -> int:
    """
    Click every Claim button on the portfolio page, confirming each modal.
    Returns the number of claims processed.
    """
    wait = WebDriverWait(driver, WAIT_TIMEOUT)

    # Reload before each search — guarantees fresh DOM and correct element positions
    driver.get(PORTFOLIO_URL)
    wait.until(EC.presence_of_element_located((By.TAG_NAME, "main")))
    time.sleep(5)

    claim_buttons = driver.find_elements(By.XPATH, _CLAIM_BTN)
    if not claim_buttons:
        return 0

    logger.info("Found %d Claim button(s), processing first...", len(claim_buttons))
    driver.execute_script("arguments[0].scrollIntoView(true);", claim_buttons[0])
    claim_buttons[0].click()

    # Wait for the confirmation modal
    try:
        confirm_btn = wait.until(EC.element_to_be_clickable((By.XPATH, _CONFIRM_BTN)))
    except TimeoutException:
        logger.error("Confirmation modal did not appear — stopping.")
        return 0

    amount = confirm_btn.text.strip()
    logger.info("Confirming: %s", amount)
    confirm_btn.click()

    # Wait for confirm modal to close
    try:
        wait.until(EC.invisibility_of_element_located((By.XPATH, _CONFIRM_BTN)))
    except TimeoutException:
        logger.warning("Confirm modal did not close cleanly — continuing anyway.")

    # Close the post-claim notification
    try:
        close_btn = wait.until(EC.element_to_be_clickable((By.XPATH, _CLOSE_BTN)))
        close_btn.click()
    except TimeoutException:
        logger.warning("No close button appeared — continuing anyway.")

    logger.info("Claimed %s: ", amount)
    time.sleep(POST_CLAIM_WAIT)

    return 1


if __name__ == "__main__":
    while True:
        chrome = launch_chrome()
        time.sleep(CHROME_STARTUP_WAIT)
        driver = make_driver()
        try:
            n = claim_all(driver)
            if n == 0:
                logger.info("No claimable positions found.")
            else:
                logger.info("Done — processed claim.")
        except Exception as e:
            logger.error("Error while running redeem script: %s", str(e))
        finally:
            driver.service.stop()
            chrome.terminate()
            chrome.wait()
            logger.info("Chrome closed.")

        logger.info("Sleeping for 5 minutes...")
        time.sleep(SLEEP_BETWEEN_RUNS)
