"""
mt5_connector.py — MT5 connection, data fetch, order management.
All MT5 calls go through this module.
"""

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None  # MT5 is Windows-only; import fails on Linux (run on Windows)

import pandas as pd
import numpy as np
import logging
from datetime import datetime
from live_trader.config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, TF_MAP

log = logging.getLogger(__name__)


# ── Connection ───────────────────────────────────────────────

def connect() -> bool:
    if not mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        log.error(f"MT5 init failed: {mt5.last_error()}")
        return False
    info = mt5.account_info()
    log.info(f"Connected: {info.login} | Balance: {info.balance} | Server: {MT5_SERVER}")
    return True


def disconnect():
    mt5.shutdown()
    log.info("MT5 disconnected.")


def is_connected() -> bool:
    return mt5.terminal_info() is not None


def get_account_info() -> dict:
    info = mt5.account_info()
    if info is None:
        return {}
    return {
        "balance" : info.balance,
        "equity"  : info.equity,
        "margin"  : info.margin,
        "free_margin": info.margin_free,
        "profit"  : info.profit,
    }


# ── Market Data ──────────────────────────────────────────────

def get_bars(symbol: str, tf_name: str, n_bars: int = 100) -> pd.DataFrame | None:
    """Fetch last n_bars OHLC for symbol/tf. Returns DataFrame or None."""
    tf = TF_MAP.get(tf_name)
    if tf is None:
        log.error(f"Unknown timeframe: {tf_name}")
        return None

    mt5.symbol_select(symbol, True)
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, n_bars)
    if rates is None or len(rates) == 0:
        log.warning(f"No data for {symbol} {tf_name}")
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.rename(columns={"time": "date_time", "tick_volume": "volume"})
    return df[["date_time", "open", "high", "low", "close", "volume"]].copy()


def get_current_price(symbol: str) -> tuple[float, float]:
    """Returns (bid, ask)."""
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return 0.0, 0.0
    return tick.bid, tick.ask


# ── Position Management ──────────────────────────────────────

def get_positions(symbol: str = None) -> list[dict]:
    """Get open positions. Filter by symbol if given."""
    positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    if positions is None:
        return []
    return [
        {
            "ticket"    : p.ticket,
            "symbol"    : p.symbol,
            "type"      : "BUY" if p.type == 0 else "SELL",
            "volume"    : p.volume,
            "open_price": p.price_open,
            "sl"        : p.sl,
            "tp"        : p.tp,
            "profit"    : p.profit,
            "comment"   : p.comment,
            "time"      : datetime.fromtimestamp(p.time),
        }
        for p in positions
    ]


def get_symbol_info(symbol: str) -> dict:
    info = mt5.symbol_info(symbol)
    if info is None:
        return {}
    return {
        "point"       : info.point,
        "digits"      : info.digits,
        "lot_min"     : info.volume_min,
        "lot_max"     : info.volume_max,
        "lot_step"    : info.volume_step,
        "contract_size": info.trade_contract_size,
        "margin_rate" : info.margin_initial,
    }


def calc_lot_size(symbol: str, sl_pct: float, risk_usd: float) -> float:
    """
    Calculate lot size from risk amount and SL%.
    risk_usd = account × risk_pct
    lot = risk_usd / (entry_price × sl_pct × contract_size)
    """
    info = get_symbol_info(symbol)
    if not info:
        return info.get("lot_min", 0.01)

    bid, ask = get_current_price(symbol)
    price = (bid + ask) / 2
    if price == 0:
        return info["lot_min"]

    contract = info["contract_size"]
    raw_lot  = risk_usd / (price * sl_pct * contract)

    # Round to lot_step
    step = info["lot_step"]
    lot  = round(raw_lot / step) * step
    lot  = max(info["lot_min"], min(lot, info["lot_max"]))
    return round(lot, 2)


# ── Order Execution ──────────────────────────────────────────

def place_order(symbol: str, direction: str, lot: float,
                sl_price: float, tp_price: float, comment: str = "") -> dict:
    """
    Place market order.
    direction: 'BUY' or 'SELL'
    Returns result dict with ticket or error.
    """
    bid, ask = get_current_price(symbol)
    info     = get_symbol_info(symbol)
    if not info:
        return {"success": False, "error": "symbol_info failed"}

    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
    price      = ask if direction == "BUY" else bid
    deviation  = 20  # slippage points

    request = {
        "action"     : mt5.TRADE_ACTION_DEAL,
        "symbol"     : symbol,
        "volume"     : lot,
        "type"       : order_type,
        "price"      : price,
        "sl"         : round(sl_price, info["digits"]),
        "tp"         : round(tp_price, info["digits"]),
        "deviation"  : deviation,
        "magic"      : 202600,
        "comment"    : comment[:31],
        "type_time"  : mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        err = result.comment if result else mt5.last_error()
        log.error(f"Order failed {symbol} {direction}: {err}")
        return {"success": False, "error": str(err)}

    log.info(f"Order placed: {symbol} {direction} {lot} lots @ {price} | SL={sl_price} TP={tp_price} | ticket={result.order}")
    return {"success": True, "ticket": result.order, "price": price}


def modify_sl(ticket: int, new_sl: float, symbol: str) -> bool:
    """Modify SL of an open position (for trailing SL2)."""
    info = get_symbol_info(symbol)
    digits = info.get("digits", 5)

    request = {
        "action"  : mt5.TRADE_ACTION_SLTP,
        "position": ticket,
        "sl"      : round(new_sl, digits),
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        log.warning(f"Modify SL failed ticket={ticket}: {result}")
        return False
    log.info(f"SL modified: ticket={ticket} new_sl={new_sl}")
    return True


def close_position(ticket: int, symbol: str, lot: float, direction: str) -> bool:
    """Close a specific position by ticket."""
    bid, ask = get_current_price(symbol)
    close_type  = mt5.ORDER_TYPE_SELL if direction == "BUY" else mt5.ORDER_TYPE_BUY
    close_price = bid if direction == "BUY" else ask

    request = {
        "action"     : mt5.TRADE_ACTION_DEAL,
        "position"   : ticket,
        "symbol"     : symbol,
        "volume"     : lot,
        "type"       : close_type,
        "price"      : close_price,
        "deviation"  : 20,
        "magic"      : 202600,
        "comment"    : "close",
        "type_time"  : mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        log.error(f"Close failed ticket={ticket}: {result}")
        return False
    log.info(f"Position closed: ticket={ticket} {symbol} {direction}")
    return True


def close_all_positions(reason: str = ""):
    """Emergency close all open positions."""
    for pos in get_positions():
        close_position(pos["ticket"], pos["symbol"], pos["volume"], pos["type"])
        log.warning(f"Emergency close: {pos['symbol']} {pos['type']} | reason={reason}")
