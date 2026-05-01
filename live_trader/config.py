"""
config.py — All settings for live trader.
Edit this file before running. Never commit real tokens to git.
"""

import os

# ── Telegram ─────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")

# ── MT5 ──────────────────────────────────────────────────────
MT5_LOGIN    = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER   = os.getenv("MT5_SERVER", "HFM-Demo")

# ── Account ──────────────────────────────────────────────────
ACCOUNT_BALANCE  = 25_000   # Starting balance (update from MT5 at runtime)
RISK_PCT         = 0.01     # 1% risk per trade

# ── FTMO Rules ───────────────────────────────────────────────
FTMO_MAX_LOSS_PCT   = 0.10   # 10% max total loss from initial balance → halt all trading
FTMO_DAILY_LOSS_PCT = 0.05   # 5% max daily loss from day-start balance → stop today
FTMO_WARN_PCT       = 0.07   # 7% DD → Telegram warning before halt
FTMO_TARGET_PCT     = 0.05   # 5% profit target (challenge phase only)

# ── Instruments & Strategy Params ────────────────────────────
# Format: symbol → {N, signal_tf, entry_tf, buffer_pct, target_pct, sl_pct}
# These are best params from grid search backtest.
INSTRUMENTS = {
    "UKOIL":   dict(N=20, signal_tf="D1", entry_tf="H4", buffer_pct=0.001,  target_pct=0.010, sl_pct=0.002),
    "XAUUSD":  dict(N=20, signal_tf="D1", entry_tf="H1", buffer_pct=0.0005, target_pct=0.003, sl_pct=0.002),
    "USDCHF":  dict(N=5,  signal_tf="D1", entry_tf="H4", buffer_pct=0.005,  target_pct=0.008, sl_pct=0.002),
    "JP225":   dict(N=20, signal_tf="D1", entry_tf="H4", buffer_pct=0.0005, target_pct=0.005, sl_pct=0.003),
    "GBPUSD":  dict(N=2,  signal_tf="H4", entry_tf="H4", buffer_pct=0.0005, target_pct=0.008, sl_pct=0.005),
    "EURCAD":  dict(N=2,  signal_tf="H4", entry_tf="H2", buffer_pct=0.0005, target_pct=0.010, sl_pct=0.020),
}

# ── SL Buffer (same as backtest) ─────────────────────────────
SL_BUFFER = 0.0012

# ── MT5 Timeframe Map ────────────────────────────────────────
TF_MAP = {
    "M15": 15, "M30": 30,
    "H1": 16385, "H2": 16386, "H4": 16388,
    "D1": 16408,
}

# ── Loop interval (seconds) ──────────────────────────────────
# Runs every bar close check. Set to 60s for H1, 240s for H4.
LOOP_SLEEP_SEC = 60

# ── Logging ──────────────────────────────────────────────────
LOG_FILE = "live_trader/trader.log"
