
import os
import time
import asyncio
import random
import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.backends.backend_pdf import PdfPages
from datetime import datetime, timedelta
from pytz import timezone
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from telegram import Bot

# Headless Chrome options for GitHub Actions
chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_argument('--disable-gpu')

# Example webdriver usage
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

# Dummy placeholder for the rest of your scraping, plotting, Telegram, CSV code
print("✅ Headless Chrome is set up properly.")

driver.quit()
