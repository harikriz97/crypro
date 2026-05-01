"""
MT5 Multi-TF Data Downloader — HFM Demo
Downloads all available symbols for: 15m, 30m, 1H, 2H, 3H, 4H, 1D
Saves to: data/mt5/{symbol}/{symbol}_{tf}.csv
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import os
import time

# ── Config ──────────────────────────────────────────────
MAX_BARS   = 9_999_999          # request max bars — broker returns what it has
OUTPUT_DIR = "data/mt5"

TIMEFRAMES = {
    "15m": mt5.TIMEFRAME_M15,
    "30m": mt5.TIMEFRAME_M30,
    "1H" : mt5.TIMEFRAME_H1,
    "2H" : mt5.TIMEFRAME_H2,
    "3H" : mt5.TIMEFRAME_H3,
    "4H" : mt5.TIMEFRAME_H4,
    "1D" : mt5.TIMEFRAME_D1,
}
# ────────────────────────────────────────────────────────


def connect():
    if not mt5.initialize():
        print(f"MT5 initialize failed: {mt5.last_error()}")
        return False
    info = mt5.terminal_info()
    print(f"Connected: {info.name} | Build: {info.build} | Demo: {info.community_account}")
    return True


def get_all_symbols():
    symbols = mt5.symbols_get()
    active = [s.name for s in symbols if s.visible or s.select]
    print(f"Total symbols found: {len(symbols)} | Active/visible: {len(active)}")
    return [s.name for s in symbols]


def download(symbol, tf_name, tf_const):
    # Enable symbol in Market Watch
    mt5.symbol_select(symbol, True)
    time.sleep(0.1)  # wait for MT5 to sync symbol data

    # Retry up to 3 times — first call may return None while MT5 loads history
    for attempt in range(3):
        rates = mt5.copy_rates_from_pos(symbol, tf_const, 0, MAX_BARS)
        if rates is not None and len(rates) > 0:
            break
        time.sleep(0.3)

    if rates is None or len(rates) == 0:
        return None

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.rename(columns={
        'time' : 'date_time',
        'open' : 'open',
        'high' : 'high',
        'low'  : 'low',
        'close': 'close',
        'tick_volume': 'volume',
        'real_volume': 'real_volume',
        'spread': 'spread'
    }, inplace=True)

    # Round OHLC to 5 decimal places (forex standard)
    for col in ['open', 'high', 'low', 'close']:
        df[col] = df[col].round(5)

    return df


def save(df, symbol, tf_name):
    folder = os.path.join(OUTPUT_DIR, symbol)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{symbol}_{tf_name}.csv")
    df.to_csv(path, index=False)
    return path


def main():
    if not connect():
        return

    symbols = get_all_symbols()
    total   = len(symbols)
    done    = 0
    skipped = 0

    print(f"\nDownloading {total} symbols x {len(TIMEFRAMES)} timeframes...\n")

    for i, symbol in enumerate(symbols, 1):
        sym_any_data = False

        for tf_name, tf_const in TIMEFRAMES.items():
            df = download(symbol, tf_name, tf_const)
            if df is not None:
                path = save(df, symbol, tf_name)
                sym_any_data = True
                print(f"[{i}/{total}] {symbol} {tf_name:>3} — {len(df):>6} bars → {path}")
            else:
                print(f"[{i}/{total}] {symbol} {tf_name:>3} — no data, skip")
                skipped += 1

        if sym_any_data:
            done += 1

        # small pause to avoid MT5 rate limits
        time.sleep(0.05)

    mt5.shutdown()
    print(f"\nDone. {done} symbols saved, {skipped} TF slots skipped (no data).")
    print(f"Output folder: {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
