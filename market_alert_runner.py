# market_alert_runner.py

import os
import requests
from datetime import datetime, timedelta

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
COUNTER_FILE = ".runlog/run_count.txt"

os.makedirs(".runlog", exist_ok=True)

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    requests.post(url, data=payload)

def read_run_count():
    try:
        with open(COUNTER_FILE, "r") as f:
            return int(f.read().strip())
    except:
        return 0

def write_run_count(count):
    with open(COUNTER_FILE, "w") as f:
        f.write(str(count))