"""
risk.py — FTMO rule enforcement + position sizing.
Checks DD limits, daily loss, halts trading if breached.
"""

import logging
from datetime import datetime, date
from live_trader.config import (
    ACCOUNT_BALANCE, RISK_PCT,
    FTMO_MAX_LOSS_PCT, FTMO_DAILY_LOSS_PCT, FTMO_WARN_PCT,
)
from live_trader.mt5_connector import get_account_info, calc_lot_size

log = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, initial_balance: float):
        self.initial_balance  = initial_balance   # Balance at account start (FTMO DD base)
        self.day_start_balance= initial_balance   # Reset at midnight CEST
        self.today            = date.today()
        self.halted_today     = False             # Daily loss halt
        self.halted_forever   = False             # Total DD halt

    # ── Daily Reset ──────────────────────────────────────────

    def check_new_day(self):
        """Call at loop start — reset daily tracking at midnight."""
        today = date.today()
        if today != self.today:
            info = get_account_info()
            self.day_start_balance = info.get("balance", self.day_start_balance)
            self.halted_today      = False
            self.today             = today
            log.info(f"New day reset | Day-start balance: {self.day_start_balance:.2f}")

    # ── FTMO Checks ──────────────────────────────────────────

    def check_limits(self) -> dict:
        """
        Run all FTMO checks. Returns status dict.
        status: 'OK' | 'WARN' | 'DAILY_HALT' | 'TOTAL_HALT'
        """
        if self.halted_forever:
            return {"status": "TOTAL_HALT", "reason": "Max loss breached"}
        if self.halted_today:
            return {"status": "DAILY_HALT", "reason": "Daily loss limit hit"}

        info    = get_account_info()
        equity  = info.get("equity", self.initial_balance)
        balance = info.get("balance", self.initial_balance)

        # 1. Total DD check (equity-based, from initial balance)
        total_dd_pct = (equity - self.initial_balance) / self.initial_balance
        if total_dd_pct <= -FTMO_MAX_LOSS_PCT:
            self.halted_forever = True
            log.critical(f"TOTAL DD BREACHED: {total_dd_pct*100:.2f}% | equity={equity:.2f}")
            return {
                "status": "TOTAL_HALT",
                "reason": f"Max loss {total_dd_pct*100:.2f}% breached",
                "equity": equity,
                "dd_pct": total_dd_pct,
            }

        # 2. Daily loss check (balance-based, from day-start)
        daily_dd_pct = (balance - self.day_start_balance) / self.initial_balance
        if daily_dd_pct <= -FTMO_DAILY_LOSS_PCT:
            self.halted_today = True
            log.warning(f"DAILY LOSS HALT: {daily_dd_pct*100:.2f}% today | balance={balance:.2f}")
            return {
                "status": "DAILY_HALT",
                "reason": f"Daily loss {daily_dd_pct*100:.2f}% breached",
                "balance": balance,
                "daily_dd_pct": daily_dd_pct,
            }

        # 3. Warning zone
        if total_dd_pct <= -FTMO_WARN_PCT:
            log.warning(f"DD WARNING: {total_dd_pct*100:.2f}% | equity={equity:.2f}")
            return {
                "status": "WARN",
                "reason": f"DD at {total_dd_pct*100:.2f}% — approaching limit",
                "equity": equity,
                "dd_pct": total_dd_pct,
                "daily_dd_pct": daily_dd_pct,
            }

        return {
            "status"      : "OK",
            "equity"      : equity,
            "balance"     : balance,
            "dd_pct"      : round(total_dd_pct * 100, 2),
            "daily_dd_pct": round(daily_dd_pct * 100, 2),
        }

    # ── Position Sizing ──────────────────────────────────────

    def get_lot_size(self, symbol: str, sl_pct: float) -> float:
        """
        Fixed-fractional: risk 1% of current balance per trade.
        Lot size = risk_usd / (price × sl_pct × contract_size)
        """
        info    = get_account_info()
        balance = info.get("balance", self.initial_balance)
        risk_usd = balance * RISK_PCT
        lot = calc_lot_size(symbol, sl_pct, risk_usd)
        log.info(f"Lot size {symbol}: sl_pct={sl_pct} risk=${risk_usd:.0f} → lot={lot}")
        return lot

    # ── Wednesday Swap Warning ───────────────────────────────

    def is_wednesday_swap_risk(self, symbol: str) -> bool:
        """Wednesday = triple swap for some instruments. Warn before open."""
        high_swap_instruments = {"XAUUSD", "UKOIL", "UKOIL"}
        return datetime.now().weekday() == 2 and symbol in high_swap_instruments

    # ── Summary ──────────────────────────────────────────────

    def daily_summary(self) -> dict:
        info = get_account_info()
        balance = info.get("balance", self.initial_balance)
        equity  = info.get("equity", self.initial_balance)
        daily_pnl = balance - self.day_start_balance
        total_pnl = balance - self.initial_balance
        return {
            "date"           : str(self.today),
            "balance"        : round(balance, 2),
            "equity"         : round(equity, 2),
            "daily_pnl"      : round(daily_pnl, 2),
            "daily_pnl_pct"  : round(daily_pnl / self.initial_balance * 100, 2),
            "total_pnl"      : round(total_pnl, 2),
            "total_pnl_pct"  : round(total_pnl / self.initial_balance * 100, 2),
            "halted_today"   : self.halted_today,
            "halted_forever" : self.halted_forever,
        }
