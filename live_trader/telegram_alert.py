"""
telegram_alert.py — All Telegram notifications.
"""

import requests
import logging
from datetime import datetime
from live_trader.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

log = logging.getLogger(__name__)

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"


def _send(text: str):
    if TELEGRAM_TOKEN == "YOUR_BOT_TOKEN":
        log.info(f"[TELEGRAM-MOCK] {text}")
        return
    try:
        resp = requests.post(BASE_URL, json={
            "chat_id"   : TELEGRAM_CHAT_ID,
            "text"      : text,
            "parse_mode": "HTML",
        }, timeout=10)
        if not resp.ok:
            log.warning(f"Telegram send failed: {resp.text}")
    except Exception as e:
        log.warning(f"Telegram error: {e}")


# ── Trade Alerts ─────────────────────────────────────────────

def alert_entry(symbol: str, direction: str, lot: float,
                entry_price: float, sl: float, tp: float, comment: str = ""):
    emoji = "🟢" if direction == "BUY" else "🔴"
    _send(
        f"{emoji} <b>ENTRY — {symbol}</b>\n"
        f"Direction : {direction}\n"
        f"Lot (x2)  : {lot}\n"
        f"Entry     : {entry_price}\n"
        f"SL        : {sl}\n"
        f"TP (Lot1) : {tp}\n"
        f"{'Comment   : ' + comment if comment else ''}\n"
        f"Time      : {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )


def alert_target_hit(symbol: str, direction: str, lot1_profit: float,
                     entry_price: float, tp: float):
    _send(
        f"🎯 <b>TARGET HIT — {symbol}</b>\n"
        f"Lot1 closed at TP\n"
        f"Direction  : {direction}\n"
        f"Entry      : {entry_price} → TP: {tp}\n"
        f"Lot1 PnL   : +${lot1_profit:.2f}\n"
        f"Lot2 trailing... (SL2 active)\n"
        f"Time       : {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )


def alert_sl_hit(symbol: str, direction: str, lot: str,
                 pnl: float, reason: str = "SL"):
    emoji = "❌" if pnl < 0 else "✅"
    _send(
        f"{emoji} <b>EXIT — {symbol} ({lot})</b>\n"
        f"Direction : {direction}\n"
        f"Reason    : {reason}\n"
        f"PnL       : {'+'if pnl>=0 else ''}${pnl:.2f}\n"
        f"Time      : {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )


def alert_sl2_update(symbol: str, direction: str, new_sl: float):
    _send(
        f"🔄 <b>SL2 UPDATED — {symbol}</b>\n"
        f"Direction : {direction}\n"
        f"New SL2   : {new_sl}\n"
        f"Time      : {datetime.now().strftime('%H:%M')}"
    )


# ── FTMO Risk Alerts ─────────────────────────────────────────

def alert_dd_warning(dd_pct: float, equity: float, daily_pct: float):
    _send(
        f"⚠️ <b>DD WARNING</b>\n"
        f"Total DD   : {dd_pct:.2f}%\n"
        f"Daily DD   : {daily_pct:.2f}%\n"
        f"Equity     : ${equity:,.2f}\n"
        f"Action     : Reduce size / be cautious\n"
        f"Time       : {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )


def alert_daily_halt(daily_pct: float, balance: float):
    _send(
        f"🚫 <b>DAILY LOSS HALT</b>\n"
        f"Daily loss : {daily_pct:.2f}% (limit 5%)\n"
        f"Balance    : ${balance:,.2f}\n"
        f"Action     : No new trades today\n"
        f"Time       : {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )


def alert_total_halt(dd_pct: float, equity: float):
    _send(
        f"🆘 <b>TOTAL LOSS HALT — ALL TRADES CLOSED</b>\n"
        f"Total DD   : {dd_pct:.2f}% (limit 10%)\n"
        f"Equity     : ${equity:,.2f}\n"
        f"Action     : ALL positions closed. Trading stopped.\n"
        f"Time       : {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )


def alert_wednesday_swap(symbol: str):
    _send(
        f"📅 <b>WEDNESDAY SWAP WARNING — {symbol}</b>\n"
        f"Today = Wednesday → 3x swap charge\n"
        f"Consider: skip new {symbol} trades today or factor in swap cost."
    )


# ── Daily Summary ────────────────────────────────────────────

def alert_daily_summary(summary: dict, trades_today: list):
    trade_lines = ""
    if trades_today:
        for t in trades_today:
            sign = "+" if t["pnl"] >= 0 else ""
            trade_lines += f"  {t['symbol']} {t['direction']} → {sign}${t['pnl']:.2f}\n"
    else:
        trade_lines = "  No trades today\n"

    pnl_sign = "+" if summary["daily_pnl"] >= 0 else ""
    _send(
        f"📊 <b>DAILY SUMMARY — {summary['date']}</b>\n"
        f"\n<b>Today:</b>\n"
        f"{trade_lines}"
        f"\n<b>Account:</b>\n"
        f"Balance    : ${summary['balance']:,.2f}\n"
        f"Daily PnL  : {pnl_sign}${summary['daily_pnl']:,.2f} ({pnl_sign}{summary['daily_pnl_pct']:.2f}%)\n"
        f"Total PnL  : ${summary['total_pnl']:,.2f} ({summary['total_pnl_pct']:+.2f}%)\n"
        f"FTMO DD    : {summary['total_pnl_pct']:+.2f}% (limit -10%)"
    )


# ── System Alerts ────────────────────────────────────────────

def alert_startup(balance: float, instruments: list):
    _send(
        f"🚀 <b>LIVE TRADER STARTED</b>\n"
        f"Balance    : ${balance:,.2f}\n"
        f"Instruments: {', '.join(instruments)}\n"
        f"FTMO rules : Daily -5% | Total -10%\n"
        f"Time       : {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )


def alert_error(context: str, error: str):
    _send(
        f"⚙️ <b>ERROR — {context}</b>\n"
        f"{error}\n"
        f"Time: {datetime.now().strftime('%H:%M')}"
    )


def alert_reconnected():
    _send(f"🔁 <b>MT5 RECONNECTED</b> — {datetime.now().strftime('%H:%M')}")
