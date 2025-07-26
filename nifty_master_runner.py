#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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

# -----------------------------------------
# ✅ CONFIGURATION
# -----------------------------------------
DEBUG_MODE = True  # Set to True for after-hours testing
STATIC_DIR = "static"
CSV_FILENAME = os.path.join(STATIC_DIR, "atm_straddle_combined.csv")
PDF_FOLDER = os.path.join(STATIC_DIR, "reports")
TODAY = datetime.now().strftime("%Y-%m-%d")
PDF_PATH = os.path.join(PDF_FOLDER, f"{TODAY}.pdf")
PNG_NIFTY_PATH = os.path.join(STATIC_DIR, "nifty_ivp_live_plot.png")
PNG_BANKNIFTY_PATH = os.path.join(STATIC_DIR, "banknifty_ivp_live_plot.png")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

print(f"TELEGRAM_TOKEN={bool(TELEGRAM_TOKEN)}, CHAT_ID={bool(TELEGRAM_CHAT_ID)}")

LOOKBACK = 30
SLEEP_INTERVAL = 300  # 5 minutes
VIX_HIGH = 16
VIX_LOW = 10
IVP_HIGH = 90
IVP_LOW = 10
VWAP_FACTOR_HIGH = 1.5
VWAP_FACTOR_LOW = 0.5

SAVE_PDF = False
SAVE_PNG = True

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
]

NIFTY_URL = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
BANKNIFTY_URL = "https://www.nseindia.com/api/option-chain-indices?symbol=BANKNIFTY"
LIVE_INDICES_URL = "https://www.nseindia.com/market-data/live-market-indices"

cookie_string = None
cookie_expiry = None

# Ensure required folders exist
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(PDF_FOLDER, exist_ok=True)

# -----------------------------------------
# ✅ SEND TELEGRAM ALERT (async-safe)
# -----------------------------------------
async def send_telegram_alert(message):
    try:
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            print("⚠️ Telegram credentials not set. Skipping alert.")
            return
        bot = Bot(token=TELEGRAM_TOKEN)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        print(f"✅ Telegram alert sent: {message}")
    except Exception as e:
        print(f"❗️ Telegram alert failed: {e}")

# -----------------------------------------
# ✅ GET NSE COOKIES
# -----------------------------------------
def get_nse_cookies():
    global cookie_string, cookie_expiry
    ist_now = datetime.now(timezone('Asia/Kolkata'))

    if cookie_string and cookie_expiry and ist_now < cookie_expiry:
        print("♻️ Reusing existing NSE cookies")
        return cookie_string

    print("⚡️ Fetching fresh NSE cookies with Selenium...")
    try:
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")

        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        driver.get("https://www.nseindia.com/option-chain")
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(random.uniform(2, 5))
        cookies = driver.get_cookies()
        cookie_string = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        cookie_expiry = ist_now + timedelta(minutes=30)
        driver.quit()
        print("✅ NSE cookies fetched")
        return cookie_string
    except Exception as e:
        print(f"❗️ Cookie fetch error: {e}")
        if 'driver' in locals():
            driver.quit()
        return None
# -----------------------------------------
# ✅ SCRAPE INDIA VIX
# -----------------------------------------
def scrape_india_vix():
    print("🔍 Scraping India VIX via Selenium...")
    try:
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")

        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        driver.get(LIVE_INDICES_URL)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "table")))
        time.sleep(random.uniform(2, 4))
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        driver.quit()

        for row in soup.find_all('tr'):
            cols = row.find_all('td')
            if any("INDIA VIX" in c.text for c in cols):
                vix_value = next((float(c.text.strip()) for c in cols if c.text.strip().replace(".", "").isdigit()), None)
                if vix_value:
                    print(f"✅ India VIX scraped: {vix_value}")
                    return vix_value
        print("❗️ India VIX not found")
        return None
    except Exception as e:
        print(f"❗️ India VIX scrape error: {e}")
        if 'driver' in locals():
            driver.quit()
        return None

# -----------------------------------------
# ✅ FETCH OPTION CHAIN
# -----------------------------------------
def fetch_option_chain(symbol, url):
    global cookie_string
    if not cookie_string:
        cookie_string = get_nse_cookies()
    if not cookie_string:
        return None

    headers = {
        "accept": "application/json",
        "user-agent": random.choice(USER_AGENTS),
        "cookie": cookie_string,
        "referer": "https://www.nseindia.com/"
    }

    for attempt in range(3):
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                print(f"✅ {symbol} option chain fetched")
                return response.json()
            else:
                print(f"⚠️ {symbol} fetch failed: HTTP {response.status_code}")
                time.sleep(2 ** attempt)
        except Exception as e:
            print(f"❗️ {symbol} fetch error: {e}")
            time.sleep(2 ** attempt)
    return None

# -----------------------------------------
# ✅ LOAD EXISTING CSV
# -----------------------------------------
def load_existing_csv():
    if os.path.exists(CSV_FILENAME):
        df = pd.read_csv(CSV_FILENAME)
        print(f"✅ Loaded existing CSV: {CSV_FILENAME} with {len(df)} rows")
        return df
    else:
        return pd.DataFrame()

# -----------------------------------------
# ✅ APPEND ONE ROW TO CSV
# -----------------------------------------
def append_row_to_csv(row_dict):
    df_existing = load_existing_csv()
    new_row = pd.DataFrame([row_dict])
    if not df_existing.empty:
        combined_df = pd.concat([df_existing, new_row], ignore_index=True)
    else:
        combined_df = new_row
    combined_df.to_csv(CSV_FILENAME, index=False)
    print(f"✅ Data appended to {CSV_FILENAME} (total rows: {len(combined_df)})")

# -----------------------------------------
# ✅ CALCULATE VWAP
# -----------------------------------------
def calculate_vwap(df_slice):
    if df_slice.empty or df_slice['total_vol'].sum() == 0:
        return None
    try:
        vwap = (df_slice['straddle'] * df_slice['total_vol']).sum() / df_slice['total_vol'].sum()
        return round(vwap, 2)
    except Exception as e:
        print(f"❗️ Error calculating VWAP: {e}")
        return None

# -----------------------------------------
# ✅ CALCULATE IVP
# -----------------------------------------
def calculate_ivp(series, current_iv):
    if series.empty:
        return None
    try:
        count = (series < current_iv).sum()
        ivp = (count / len(series)) * 100
        return round(ivp, 1)
    except Exception as e:
        print(f"❗️ Error calculating IVP: {e}")
        return None
# -----------------------------------------
# ✅ PREPARE COMBINED ROW
# -----------------------------------------
def prepare_combined_row(timestamp, india_vix, nifty_data, banknifty_data):
    combined_row = {"timestamp": timestamp}
    if india_vix is not None:
        combined_row["india_vix"] = round(india_vix, 2)

    for symbol, data in [("NIFTY", nifty_data), ("BANKNIFTY", banknifty_data)]:
        spot_price = data['records']['underlyingValue']
        expiry_dates = sorted(
            data['records']['expiryDates'],
            key=lambda x: datetime.strptime(x, "%d-%b-%Y").date()
        )
        chosen_expiries = expiry_dates[:2]

        for i, expiry in enumerate(chosen_expiries):
            all_strikes = [
                item['strikePrice'] for item in data['records']['data']
                if item['expiryDate'] == expiry
            ]
            atm_strike = min(all_strikes, key=lambda x: abs(x - spot_price))

            ce_data = next((
                item.get('CE') for item in data['records']['data']
                if item['expiryDate'] == expiry and item['strikePrice'] == atm_strike and 'CE' in item
            ), {})
            pe_data = next((
                item.get('PE') for item in data['records']['data']
                if item['expiryDate'] == expiry and item['strikePrice'] == atm_strike and 'PE' in item
            ), {})

            call_ltp = ce_data.get('lastPrice', 0)
            put_ltp = pe_data.get('lastPrice', 0)
            call_vol = ce_data.get('totalTradedVolume', 0)
            put_vol = pe_data.get('totalTradedVolume', 0)
            call_iv = ce_data.get('impliedVolatility', 0)
            put_iv = pe_data.get('impliedVolatility', 0)

            straddle_premium = call_ltp + put_ltp
            total_vol = call_vol + put_vol
            straddle_iv = round(call_iv + put_iv, 1)

            label = f"{symbol.lower()}_{'curr' if i == 0 else 'next'}"

            combined_row[f"{label}_expiry"] = expiry
            combined_row[f"{label}_strike"] = atm_strike
            if i == 0:
                combined_row[f"{label}_spot"] = round(spot_price, 1)
            combined_row[f"{label}_call_ltp"] = call_ltp
            combined_row[f"{label}_put_ltp"] = put_ltp
            combined_row[f"{label}_straddle"] = straddle_premium
            combined_row[f"{label}_call_vol"] = call_vol
            combined_row[f"{label}_put_vol"] = put_vol
            combined_row[f"{label}_total_vol"] = total_vol
            combined_row[f"{label}_call_iv"] = call_iv
            combined_row[f"{label}_put_iv"] = put_iv
            combined_row[f"{label}_straddle_iv"] = straddle_iv

            df_existing = load_existing_csv()
            df_existing.columns = [col.lower() for col in df_existing.columns]
            filter_cols = [col for col in df_existing.columns if label in col]
            df_symbol_expiry = df_existing[["timestamp"] + filter_cols] if not df_existing.empty else pd.DataFrame()
            df_symbol_expiry = df_symbol_expiry.tail(LOOKBACK)

            if not df_symbol_expiry.empty:
                df_symbol_expiry = df_symbol_expiry.rename(columns={
                    f"{label}_straddle": "straddle",
                    f"{label}_total_vol": "total_vol"
                })
            vwap = calculate_vwap(df_symbol_expiry)
            ivp = calculate_ivp(df_symbol_expiry.get(f"{label}_straddle_iv", pd.Series()), straddle_iv)

            print(f"[{label}] Current IV: {straddle_iv}, IVP: {ivp}")

            combined_row[f"{label}_vwap"] = vwap
            combined_row[f"{label}_ivp"] = ivp

            if ivp is not None and (ivp > IVP_HIGH or ivp < IVP_LOW):
                asyncio.run(send_telegram_alert(
                    f"⚠️ {symbol} {expiry}: IVP Alert! IVP={ivp}% at {timestamp}"
                ))

            if vwap is not None and vwap != 0:
                if (straddle_premium > VWAP_FACTOR_HIGH * vwap) or (straddle_premium < VWAP_FACTOR_LOW * vwap):
                    asyncio.run(send_telegram_alert(
                        f"⚠️ {symbol} {expiry}: Straddle Premium Alert! Premium={straddle_premium}, VWAP={vwap} at {timestamp}"
                    ))

    return combined_row
# -----------------------------------------
# ✅ GENERATE IVP PLOTS (PNG + PDF)
# -----------------------------------------
def generate_ivp_plots():
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.backends.backend_pdf import PdfPages

    print(f"🖼️ Generating IVP Plots...")

    try:
        df = load_existing_csv()
        if df.empty:
            print("⚠️ No data in CSV to plot")
            return

        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp'])
        df = df.sort_values("timestamp")

        if 'india_vix' not in df.columns:
            df['india_vix'] = None
        df['india_vix'] = df['india_vix'].ffill()

        df_nifty = df[[c for c in df.columns if 'nifty' in c.lower()] + ['timestamp', 'india_vix']].copy()
        df_banknifty = df[[c for c in df.columns if 'banknifty' in c.lower()] + ['timestamp', 'india_vix']].copy()

        if df_nifty.empty or df_banknifty.empty:
            print("⚠️ Not enough NIFTY or BANKNIFTY data to plot")
            return

        os.makedirs("static", exist_ok=True)
        os.makedirs("reports", exist_ok=True)
        date_str = datetime.now(timezone("Asia/Kolkata")).strftime('%Y-%m-%d')
        pdf_path = f"reports/{date_str}.pdf"
        pdf = PdfPages(pdf_path)

        def format_axes(ax):
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
            ax.tick_params(axis='x', rotation=45)

        def plot_symbol(df_sym, prefix, png_path, title_prefix):
            fig, axes = plt.subplots(3, 1, figsize=(14, 14), sharex=True)
            plt.subplots_adjust(hspace=0.5)

            # Subplot 1: VIX + IV
            ax1 = axes[0]
            ax1.plot(df_sym['timestamp'], df_sym['india_vix'], label='India VIX', color='red', linestyle='--', linewidth=2)
            ax1.set_ylabel("India VIX", color='red')
            ax1.set_title(f"VIX & IV vs Time ({title_prefix})")

            if f'{prefix}_curr_straddle_iv' in df_sym.columns and f'{prefix}_next_straddle_iv' in df_sym.columns:
                ax1b = ax1.twinx()
                ax1b.plot(df_sym['timestamp'], df_sym[f'{prefix}_curr_straddle_iv'], label='Curr IV', color='blue', linewidth=2)
                ax1b.plot(df_sym['timestamp'], df_sym[f'{prefix}_next_straddle_iv'], label='Next IV', color='orange', linewidth=2)
                ax1b.set_ylabel("Straddle IV", color='blue')
                ax1b.legend(loc='upper left')
            ax1.legend(loc='lower left')

            # Subplot 2: Spot vs Premium + VWAP
            ax2 = axes[1]
            ax2.plot(df_sym['timestamp'], df_sym.get(f'{prefix}_curr_spot', []), label='Spot', color='black', linewidth=2)
            ax2b = ax2.twinx()
            if f'{prefix}_curr_straddle' in df_sym.columns:
                ax2b.plot(df_sym['timestamp'], df_sym[f'{prefix}_curr_straddle'], label='Curr Premium', color='blue', linewidth=2)
            if f'{prefix}_curr_vwap' in df_sym.columns:
                ax2b.plot(df_sym['timestamp'], df_sym[f'{prefix}_curr_vwap'], label='Curr VWAP', color='blue', linestyle='--', linewidth=2)
            if f'{prefix}_next_straddle' in df_sym.columns:
                ax2b.plot(df_sym['timestamp'], df_sym[f'{prefix}_next_straddle'], label='Next Premium', color='orange', linewidth=2)
            if f'{prefix}_next_vwap' in df_sym.columns:
                ax2b.plot(df_sym['timestamp'], df_sym[f'{prefix}_next_vwap'], label='Next VWAP', color='orange', linestyle='--', linewidth=2)
            ax2.set_ylabel("Spot")
            ax2b.set_ylabel("Straddle / VWAP")
            ax2.set_title(f"Spot vs Straddle Premium & VWAP ({title_prefix})")
            ax2.legend(loc='lower left')
            ax2b.legend(loc='upper left')

            # Subplot 3: Spot vs IVP%
            ivp_curr_col = f'{prefix}_curr_ivp'
            ivp_next_col = f'{prefix}_next_ivp'
            if ivp_curr_col in df_sym.columns and ivp_next_col in df_sym.columns:
                ax3 = axes[2]
                ax3.plot(df_sym['timestamp'], df_sym[f'{prefix}_curr_spot'], label='Spot Price', color='black', linewidth=2)
                ax3b = ax3.twinx()
                ax3b.plot(df_sym['timestamp'], df_sym[ivp_curr_col], label='Curr IVP%', color='green', linewidth=2)
                ax3b.plot(df_sym['timestamp'], df_sym[ivp_next_col], label='Next IVP%', color='darkorange', linewidth=2)
                ax3.set_ylabel('Spot Price', color='black')
                ax3b.set_ylabel('IVP %', color='green')
                ax3.set_title(f"Spot vs IVP% ({title_prefix})")
                ax3.legend(loc='lower left')
                ax3b.legend(loc='upper left')
                format_axes(ax3)
            else:
                print(f"⚠️ Skipping IVP% subplot for {prefix}: IVP columns not found")

            format_axes(ax1)
            format_axes(ax2)

            plt.tight_layout()
            if SAVE_PDF:
                pdf.savefig(fig)
            if SAVE_PNG:
                fig.savefig(png_path)
                print(f"✅ PNG Saved: {png_path}")
            plt.close(fig)

        plot_symbol(df_nifty, 'nifty', 'static/nifty_ivp_live_plot.png', 'NIFTY')
        plot_symbol(df_banknifty, 'banknifty', 'static/banknifty_ivp_live_plot.png', 'BANKNIFTY')

        if SAVE_PDF:
            pdf.close()
            print(f"✅ PDF Saved: {pdf_path}")

    except Exception as e:
        print(f"❌ Error in generate_ivp_plots(): {e}")
# -----------------------------------------
# ✅ MASTER MAIN LOGIC (GitHub Actions Version)
# -----------------------------------------
if __name__ == "__main__":
    print("✅ Starting GitHub Actions NSE Monitor...")

    india_time = datetime.now(timezone('Asia/Kolkata'))
    timestamp = india_time.strftime("%Y-%m-%d %H:%M:%S")

    # DEBUG mode always allowed. Else: Only during market hours.
    market_open = (
        DEBUG_MODE or (
            (india_time.hour == 9 and india_time.minute >= 15) or
            (10 <= india_time.hour < 15) or
            (india_time.hour == 15 and india_time.minute <= 30)
        )
    )

    if not market_open:
        print("⏳ Market closed. Exiting gracefully...")
        exit()

    try:
        india_time_str = india_time.strftime("%H:%M")
        india_vix = scrape_india_vix()

        if india_vix is not None:
            rounded_vix = round(india_vix, 2)
            print(f"✅ India VIX: {rounded_vix} (Checking thresholds: LOW={VIX_LOW}, HIGH={VIX_HIGH})")

            if rounded_vix >= VIX_HIGH or rounded_vix <= VIX_LOW:
                alert_msg = f"⚠️ India VIX Alert! VIX={rounded_vix} at {timestamp}"
                print(f"⚡️ TRIGGERING ALERT: {alert_msg}")
                asyncio.run(send_telegram_alert(alert_msg))
        else:
            print("⚠️ India VIX scrape returned None")

        # --- Step 2️⃣: Fetch Option Chains
        nifty_data = fetch_option_chain("NIFTY", NIFTY_URL)
        banknifty_data = fetch_option_chain("BANKNIFTY", BANKNIFTY_URL)

        if not nifty_data or not banknifty_data:
            print("❗️ Option chain fetch failed. Exiting...")
            exit()

        # --- Step 3️⃣: Prepare Combined Row
        combined_row = prepare_combined_row(timestamp, india_vix, nifty_data, banknifty_data)
        if combined_row:
            append_row_to_csv(combined_row)

        # --- Step 4️⃣: Generate PNG & PDF
        generate_ivp_plots()

        print("✅ Script completed one cycle and will now exit.")

    except Exception as e:
        error_msg = f"❗️ Error in GitHub Actions run: {str(e)}"
        print(error_msg)
        try:
            asyncio.run(send_telegram_alert(error_msg))
        except Exception as te:
            print(f"❗️ Telegram send error: {te}")
        exit(1)

# ✅ Increment run count (even if outside try block)
try:
    from market_alert_runner import read_run_count, write_run_count
    count = read_run_count()
    write_run_count(count + 1)
    print(f"📟 Run count updated to: {count + 1}")
except Exception as e:
    print("⚠️ Failed to update run count:", e)
