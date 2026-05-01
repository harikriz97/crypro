"""
trader.py — Main trading loop.
One cycle per entry_tf bar close. Handles all instruments.

Trade Cycle (per instrument):
  1. FTMO risk check
  2. If position open → manage (check SL2 trail, target hit)
  3. If no position → check signal → entry
  4. Sequential: one position at a time per instrument (Rule 9)
"""

import logging
import time
from datetime import datetime
from dataclasses import dataclass, field

from live_trader import config
from live_trader.mt5_connector import (
    get_positions, get_current_price,
    place_order, modify_sl, close_position, close_all_positions,
)
from live_trader.signal import get_signal_levels, check_entry, calc_sl_tp, calc_sl2
from live_trader.risk import RiskManager
from live_trader import telegram_alert as tg

log = logging.getLogger(__name__)


# ── State per instrument ─────────────────────────────────────

@dataclass
class InstrumentState:
    symbol      : str
    lot1_ticket : int   = 0       # Lot1 (closes at TP)
    lot2_ticket : int   = 0       # Lot2 (trails with SL2)
    direction   : str   = ""      # 'BUY' or 'SELL'
    entry_price : float = 0.0
    sl1         : float = 0.0
    tp          : float = 0.0
    sl2         : float = 0.0
    lot1_hit    : bool  = False   # True once Lot1 TP hit
    active      : bool  = False
    rev_watch   : str   = ""      # 'BUY' or 'SELL' — reversal watch


# ── Main Trader ──────────────────────────────────────────────

class Trader:
    def __init__(self):
        from live_trader.mt5_connector import get_account_info
        info             = get_account_info()
        initial_balance  = info.get("balance", config.ACCOUNT_BALANCE)
        self.risk        = RiskManager(initial_balance)
        self.states      = {sym: InstrumentState(sym) for sym in config.INSTRUMENTS}
        self.trades_today: list[dict] = []
        log.info(f"Trader init | balance={initial_balance:.2f} | instruments={list(config.INSTRUMENTS.keys())}")
        tg.alert_startup(initial_balance, list(config.INSTRUMENTS.keys()))

    # ── Single Cycle ─────────────────────────────────────────

    def run_cycle(self):
        self.risk.check_new_day()
        risk_status = self.risk.check_limits()

        # Total halt → close everything
        if risk_status["status"] == "TOTAL_HALT":
            tg.alert_total_halt(
                risk_status.get("dd_pct", 0) * 100,
                risk_status.get("equity", 0)
            )
            close_all_positions("TOTAL_HALT")
            return

        # Daily halt → manage open positions only, no new entries
        allow_entry = risk_status["status"] not in ("DAILY_HALT", "TOTAL_HALT")
        if risk_status["status"] == "DAILY_HALT" and not self.risk.halted_today:
            tg.alert_daily_halt(
                risk_status.get("daily_dd_pct", 0),
                risk_status.get("balance", 0)
            )

        if risk_status["status"] == "WARN":
            tg.alert_dd_warning(
                risk_status["dd_pct"],
                risk_status["equity"],
                risk_status["daily_dd_pct"],
            )

        for symbol, params in config.INSTRUMENTS.items():
            try:
                self._process_instrument(symbol, params, allow_entry)
            except Exception as e:
                log.error(f"Error processing {symbol}: {e}", exc_info=True)
                tg.alert_error(symbol, str(e))

    # ── Instrument Logic ─────────────────────────────────────

    def _process_instrument(self, symbol: str, params: dict, allow_entry: bool):
        state  = self.states[symbol]
        levels = get_signal_levels(symbol, params)
        if levels is None:
            return

        # ── Manage open position ──────────────────────────────
        if state.active:
            self._manage_position(symbol, params, state, levels)
            return

        # ── Look for new entry ────────────────────────────────
        if not allow_entry:
            return

        # Wednesday swap warning for high-swap instruments
        if self.risk.is_wednesday_swap_risk(symbol):
            tg.alert_wednesday_swap(symbol)
            return  # skip new entries on Wednesday for these

        # Check entry signal
        signal = check_entry(symbol, params, levels)

        # Reversal watch override
        if state.rev_watch:
            if signal == state.rev_watch:
                self._open_position(symbol, params, state, levels, signal)
            # else: wait for reversal signal
            return

        if signal:
            self._open_position(symbol, params, state, levels, signal)

    # ── Open Position ────────────────────────────────────────

    def _open_position(self, symbol: str, params: dict,
                       state: InstrumentState, levels: dict, direction: str):
        sl_pct = params["sl_pct"]
        lot    = self.risk.get_lot_size(symbol, sl_pct)
        if lot <= 0:
            log.warning(f"{symbol}: lot size 0, skipping")
            return

        bid, ask   = get_current_price(symbol)
        entry_price = ask if direction == "BUY" else bid
        sl1, tp    = calc_sl_tp(direction, entry_price, params, levels)

        # Place Lot1 (with TP)
        r1 = place_order(symbol, direction, lot, sl1, tp, comment="Lot1")
        if not r1["success"]:
            return

        # Place Lot2 (same SL, NO TP — trails manually)
        r2 = place_order(symbol, direction, lot, sl1, 0.0, comment="Lot2")
        if not r2["success"]:
            close_position(r1["ticket"], symbol, lot, direction)
            return

        # Update state
        state.lot1_ticket = r1["ticket"]
        state.lot2_ticket = r2["ticket"]
        state.direction   = direction
        state.entry_price = entry_price
        state.sl1         = sl1
        state.tp          = tp
        state.sl2         = sl1   # SL2 starts same as SL1
        state.lot1_hit    = False
        state.active      = True
        state.rev_watch   = ""

        log.info(f"ENTRY {symbol} {direction} x2 @ {entry_price} | SL={sl1} TP={tp}")
        tg.alert_entry(symbol, direction, lot * 2, entry_price, sl1, tp)

    # ── Manage Open Position ─────────────────────────────────

    def _manage_position(self, symbol: str, params: dict,
                         state: InstrumentState, levels: dict):
        open_positions = {p["ticket"]: p for p in get_positions(symbol)}

        lot1_open = state.lot1_ticket in open_positions
        lot2_open = state.lot2_ticket in open_positions

        # Both closed externally (SL hit via broker)
        if not lot1_open and not lot2_open:
            pnl = self._record_exit(symbol, state, "SL/Broker close")
            self._reset_state(state, flip_watch=True)
            return

        # Lot1 closed (TP hit) — start trailing Lot2
        if not lot1_open and lot2_open and not state.lot1_hit:
            state.lot1_hit = True
            lot1_pnl = open_positions.get(state.lot1_ticket, {}).get("profit", 0)
            log.info(f"{symbol} Lot1 TP HIT | switching to SL2 trail")
            tg.alert_target_hit(symbol, state.direction, lot1_pnl, state.entry_price, state.tp)

        # Lot2 closed (SL2 hit) — trade over
        if state.lot1_hit and not lot2_open:
            pnl = self._record_exit(symbol, state, "SL2")
            self._reset_state(state, flip_watch=False)
            return

        # Update trailing SL2 on Lot2
        if state.lot1_hit and lot2_open:
            new_sl2 = calc_sl2(state.direction, state.entry_price, params, levels)
            improved = (
                (state.direction == "BUY"  and new_sl2 > state.sl2) or
                (state.direction == "SELL" and new_sl2 < state.sl2)
            )
            if improved:
                ok = modify_sl(state.lot2_ticket, new_sl2, symbol)
                if ok:
                    old_sl2 = state.sl2
                    state.sl2 = new_sl2
                    log.info(f"{symbol} SL2 trail: {old_sl2} → {new_sl2}")
                    tg.alert_sl2_update(symbol, state.direction, new_sl2)

    # ── Helpers ──────────────────────────────────────────────

    def _record_exit(self, symbol: str, state: InstrumentState, reason: str) -> float:
        from live_trader.mt5_connector import get_account_info
        info = get_account_info()
        pnl  = info.get("profit", 0)  # approximate
        log.info(f"EXIT {symbol} {state.direction} | reason={reason}")
        tg.alert_sl_hit(symbol, state.direction, "Lot2" if state.lot1_hit else "Both", pnl, reason)
        self.trades_today.append({
            "symbol"   : symbol,
            "direction": state.direction,
            "pnl"      : pnl,
            "reason"   : reason,
        })
        return pnl

    def _reset_state(self, state: InstrumentState, flip_watch: bool):
        direction = state.direction
        state.lot1_ticket = 0
        state.lot2_ticket = 0
        state.entry_price = 0.0
        state.sl1 = state.tp = state.sl2 = 0.0
        state.lot1_hit = False
        state.active   = False
        # Reversal: if SL hit before target → watch for opposite
        if flip_watch and not state.lot1_hit:
            state.rev_watch = "SELL" if direction == "BUY" else "BUY"
        else:
            state.rev_watch = ""

    # ── End of Day Summary ───────────────────────────────────

    def send_daily_summary(self):
        summary = self.risk.daily_summary()
        tg.alert_daily_summary(summary, self.trades_today)
        self.trades_today = []
        log.info(f"Daily summary sent | PnL={summary['daily_pnl']:.2f}")
