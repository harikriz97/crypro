"""
signal.py — N-Bar Breakout signal generation.
Computes NDH/NDL from signal_tf, detects entry on entry_tf.
Matches backtest logic exactly (forward-bias safe).
"""

import numpy as np
import pandas as pd
import logging
from live_trader.mt5_connector import get_bars
from live_trader.config import SL_BUFFER

log = logging.getLogger(__name__)


def get_signal_levels(symbol: str, params: dict) -> dict | None:
    """
    Compute NDH, NDL, NDH2, NDL2 from signal_tf.
    Returns dict with levels or None if data unavailable.
    """
    N         = params["N"]
    signal_tf = params["signal_tf"]

    # Need N+2 closed bars (shift(1) means we skip the current open bar)
    df = get_bars(symbol, signal_tf, n_bars=N + 10)
    if df is None or len(df) < N + 2:
        log.warning(f"{symbol} signal: not enough bars ({len(df) if df is not None else 0})")
        return None

    # Exclude last bar (currently forming — forward bias prevention)
    df = df.iloc[:-1].reset_index(drop=True)

    highs = df["high"].values
    lows  = df["low"].values

    # NDH = max of last N bars (shift 1 = exclude current bar already done above)
    ndh  = float(np.max(highs[-N:]))
    ndl  = float(np.min(lows[-N:]))
    ndh2 = float(np.max(highs[-2:]))
    ndl2 = float(np.min(lows[-2:]))

    buy_level  = round(ndh * (1 + params["buffer_pct"]), 5)
    sell_level = round(ndl * (1 - params["buffer_pct"]), 5)

    return {
        "NDH"       : ndh,
        "NDL"       : ndl,
        "NDH2"      : ndh2,
        "NDL2"      : ndl2,
        "buy_level" : buy_level,
        "sell_level": sell_level,
    }


def check_entry(symbol: str, params: dict, levels: dict) -> str | None:
    """
    Check if current entry_tf bar triggers a breakout.
    Returns 'BUY', 'SELL', or None.
    Uses entry_signal_time rule: only trade on NEXT bar open + 2 sec (Rule 8).
    In live trading: check if current bar's high/low crosses level.
    """
    entry_tf = params["entry_tf"]
    df = get_bars(symbol, entry_tf, n_bars=3)
    if df is None or len(df) < 2:
        return None

    # Use last CLOSED bar (bar[-2]), not current forming bar
    bar = df.iloc[-2]
    bar_h = float(bar["high"])
    bar_l = float(bar["low"])
    bar_o = float(bar["open"])

    buy_lv  = levels["buy_level"]
    sell_lv = levels["sell_level"]

    hit_buy  = bar_h >= buy_lv
    hit_sell = bar_l <= sell_lv

    if hit_buy and not hit_sell:
        return "BUY"
    elif hit_sell and not hit_buy:
        return "SELL"
    elif hit_buy and hit_sell:
        # Both hit same bar — use open to decide
        mid = (buy_lv + sell_lv) / 2
        return "BUY" if bar_o >= mid else "SELL"

    return None


def calc_sl_tp(direction: str, entry_price: float, params: dict, levels: dict) -> tuple[float, float]:
    """
    Compute SL1 and TP for Lot1.
    SL1 = max(entry × (1 - sl_pct), NDL2 × (1 - SL_BUFFER))  for BUY
    TP  = entry × (1 + target_pct)                            for BUY
    """
    sl_pct     = params["sl_pct"]
    target_pct = params["target_pct"]

    if direction == "BUY":
        sl = max(
            entry_price * (1 - sl_pct),
            levels["NDL2"] * (1 - SL_BUFFER)
        )
        tp = entry_price * (1 + target_pct)
    else:
        sl = min(
            entry_price * (1 + sl_pct),
            levels["NDH2"] * (1 + SL_BUFFER)
        )
        tp = entry_price * (1 - target_pct)

    return round(sl, 5), round(tp, 5)


def calc_sl2(direction: str, entry_price: float, params: dict, levels: dict) -> float:
    """
    Trailing SL2 (after target hit).
    SL2 = max(entry × (1 - sl_pct), NDL × (1 - SL_BUFFER))  for BUY
    Updated each bar with fresh NDL.
    """
    sl_pct = params["sl_pct"]

    if direction == "BUY":
        sl2 = max(
            entry_price * (1 - sl_pct),
            levels["NDL"] * (1 - SL_BUFFER)
        )
    else:
        sl2 = min(
            entry_price * (1 + sl_pct),
            levels["NDH"] * (1 + SL_BUFFER)
        )

    return round(sl2, 5)
