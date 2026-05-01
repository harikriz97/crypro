"""
yfinance Multi-TF Data Downloader
Forex, Commodity, Crypto, Indices — no MT5 needed
Saves to: data/yf/{symbol}/{symbol}_{tf}.csv

Run: python yf_download.py
"""

import yfinance as yf
import pandas as pd
import os
import time

OUTPUT_DIR = "data/yf"

# ── Symbol Map: friendly name → yfinance ticker ──────────
SYMBOLS = {
    # Forex
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
    "USDCHF": "USDCHF=X", "AUDUSD": "AUDUSD=X", "NZDUSD": "NZDUSD=X",
    "USDCAD": "USDCAD=X", "EURGBP": "EURGBP=X", "EURJPY": "EURJPY=X",
    "GBPJPY": "GBPJPY=X", "AUDJPY": "AUDJPY=X", "CADJPY": "CADJPY=X",
    "CHFJPY": "CHFJPY=X", "EURAUD": "EURAUD=X", "EURCHF": "EURCHF=X",
    "EURCAD": "EURCAD=X", "GBPAUD": "GBPAUD=X", "GBPCAD": "GBPCAD=X",
    "GBPCHF": "GBPCHF=X", "AUDCAD": "AUDCAD=X", "AUDCHF": "AUDCHF=X",
    "AUDNZD": "AUDNZD=X", "NZDCAD": "NZDCAD=X", "NZDCHF": "NZDCHF=X",
    "NZDJPY": "NZDJPY=X", "USDSGD": "USDSGD=X", "USDHKD": "USDHKD=X",
    "USDMXN": "USDMXN=X", "USDZAR": "USDZAR=X", "USDTRY": "USDTRY=X",
    "USDSEK": "USDSEK=X", "USDNOK": "USDNOK=X", "USDDKK": "USDDKK=X",
    "USDPLN": "USDPLN=X", "USDHUF": "USDHUF=X", "USDCZK": "USDCZK=X",

    # Metals / Commodities
    "XAUUSD": "GC=F",   # Gold futures
    "XAGUSD": "SI=F",   # Silver futures
    "USOIL" : "CL=F",   # WTI Crude Oil
    "UKOIL" : "BZ=F",   # Brent Crude
    "Copper": "HG=F",
    "Platinum": "PL=F",
    "Palladium": "PA=F",
    "NatGas": "NG=F",
    "Corn"  : "ZC=F",
    "Wheat" : "ZW=F",
    "Soybean": "ZS=F",
    "Sugar" : "SB=F",
    "Coffee": "KC=F",
    "Cotton": "CT=F",

    # Indices
    "US500" : "ES=F",   # S&P 500 futures
    "USA100": "NQ=F",   # Nasdaq futures
    "USA30" : "YM=F",   # Dow Jones futures
    "UK100" : "^FTSE",
    "GER40" : "^GDAXI",
    "FRA40" : "^FCHI",
    "JPN225": "^N225",
    "AUS200": "^AXJO",
    "HK50"  : "^HSI",
    "EU50"  : "^STOXX50E",

    # Crypto
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
    "XRPUSD": "XRP-USD",
    "LTCUSD": "LTC-USD",
    "ADAUSD": "ADA-USD",
    "SOLUSD": "SOL-USD",
    "BNBUSD": "BNB-USD",
    "DOTUSD": "DOT-USD",
    "AVAXUSD": "AVAX-USD",
    "LINKUSD": "LINK-USD",
    "DOGEUSD": "DOGE-USD",
    "XLMUSD": "XLM-USD",
    "ATOMUSD": "ATOM-USD",
    "UNIUSD": "UNI-USD",
    "TRXUSD": "TRX-USD",
}

# ── Timeframe config ──────────────────────────────────────
# yfinance intervals: 1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo
# 2H/3H = not native → resample from 1H
# History limits: 15m/30m=60d, 1H=730d, 1D=max

TF_NATIVE = {
    "15m": {"interval": "15m", "period": "60d"},
    "30m": {"interval": "30m", "period": "60d"},
    "1H" : {"interval": "1h",  "period": "730d"},
    "1D" : {"interval": "1d",  "period": "max"},
}

TF_RESAMPLE = {
    "2H": "2h",
    "3H": "3h",
    "4H": "4h",
}
# ─────────────────────────────────────────────────────────


def fetch_native(ticker, interval, period):
    try:
        df = yf.download(ticker, period=period, interval=interval,
                         auto_adjust=True, progress=False)
        if df is None or df.empty:
            return None
        df.index.name = "date_time"
        df = df.reset_index()
        df.columns = [c.lower() if isinstance(c, str) else c[0].lower()
                      for c in df.columns]
        df = df.rename(columns={"date_time": "date_time"})
        for col in ["open", "high", "low", "close"]:
            if col in df.columns:
                df[col] = df[col].round(5)
        return df
    except Exception as e:
        return None


def resample_to_tf(df_1h, rule):
    df = df_1h.set_index("date_time")
    resampled = df.resample(rule).agg({
        "open" : "first",
        "high" : "max",
        "low"  : "min",
        "close": "last",
        "volume": "sum"
    }).dropna(subset=["open"])
    resampled = resampled.reset_index()
    for col in ["open", "high", "low", "close"]:
        resampled[col] = resampled[col].round(5)
    return resampled


def save(df, symbol, tf_name):
    folder = os.path.join(OUTPUT_DIR, symbol)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{symbol}_{tf_name}.csv")
    df.to_csv(path, index=False)
    return path


def main():
    total = len(SYMBOLS)
    done = 0

    print(f"Downloading {total} symbols × {len(TF_NATIVE) + len(TF_RESAMPLE)} timeframes...\n")

    for i, (symbol, ticker) in enumerate(SYMBOLS.items(), 1):

        # -- Native TFs --
        df_1h = None
        for tf_name, cfg in TF_NATIVE.items():
            df = fetch_native(ticker, cfg["interval"], cfg["period"])
            if df is not None:
                path = save(df, symbol, tf_name)
                print(f"[{i}/{total}] {symbol:10} {tf_name:>3} — {len(df):>5} bars → {path}")
                if tf_name == "1H":
                    df_1h = df
                done += 1
            else:
                print(f"[{i}/{total}] {symbol:10} {tf_name:>3} — no data")

        # -- Resampled TFs (2H, 3H, 4H from 1H) --
        if df_1h is not None:
            for tf_name, rule in TF_RESAMPLE.items():
                try:
                    df_rs = resample_to_tf(df_1h, rule)
                    if not df_rs.empty:
                        path = save(df_rs, symbol, tf_name)
                        print(f"[{i}/{total}] {symbol:10} {tf_name:>3} — {len(df_rs):>5} bars → {path}")
                        done += 1
                except Exception:
                    print(f"[{i}/{total}] {symbol:10} {tf_name:>3} — resample failed")
        else:
            for tf_name in TF_RESAMPLE:
                print(f"[{i}/{total}] {symbol:10} {tf_name:>3} — skipped (no 1H base)")

        time.sleep(0.3)  # avoid rate limit

    print(f"\nDone. {done} files saved → {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
