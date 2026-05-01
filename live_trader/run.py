"""
run.py — Entry point for live trader.
Handles MT5 reconnection, daily summary, graceful shutdown.

Usage:
  # Set env vars first:
  export MT5_LOGIN=12345678
  export MT5_PASSWORD=yourpassword
  export MT5_SERVER=HFM-Demo
  export TELEGRAM_TOKEN=your_bot_token
  export TELEGRAM_CHAT_ID=your_chat_id

  python run.py

  # Or on Windows MT5 machine:
  python live_trader/run.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import logging
import signal
from datetime import datetime, time as dtime

from live_trader import config
from live_trader import telegram_alert as tg
from live_trader.mt5_connector import connect, disconnect, is_connected
from live_trader.trader import Trader

# ── Logging setup ────────────────────────────────────────────
os.makedirs("live_trader", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("run")

# ── Graceful shutdown ─────────────────────────────────────────
_running = True

def _shutdown(signum, frame):
    global _running
    log.info("Shutdown signal received.")
    _running = False

signal.signal(signal.SIGINT,  _shutdown)
signal.signal(signal.SIGTERM, _shutdown)


# ── Helpers ──────────────────────────────────────────────────

DAILY_SUMMARY_TIME = dtime(17, 0)   # Send summary at 17:00 daily
_last_summary_date = None

def _should_send_summary() -> bool:
    global _last_summary_date
    now = datetime.now()
    if now.time() >= DAILY_SUMMARY_TIME and _last_summary_date != now.date():
        _last_summary_date = now.date()
        return True
    return False


def _reconnect(max_retries=5) -> bool:
    for attempt in range(1, max_retries + 1):
        log.warning(f"MT5 reconnect attempt {attempt}/{max_retries}...")
        if connect():
            tg.alert_reconnected()
            return True
        time.sleep(30)
    return False


# ── Main Loop ────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("  LIVE TRADER STARTING")
    log.info(f"  Instruments : {list(config.INSTRUMENTS.keys())}")
    log.info(f"  Risk/trade  : {config.RISK_PCT*100}%")
    log.info(f"  FTMO daily  : -{config.FTMO_DAILY_LOSS_PCT*100}%")
    log.info(f"  FTMO total  : -{config.FTMO_MAX_LOSS_PCT*100}%")
    log.info("=" * 60)

    if not connect():
        log.critical("Cannot connect to MT5. Exiting.")
        sys.exit(1)

    trader = Trader()

    while _running:
        try:
            # Reconnect if dropped
            if not is_connected():
                log.warning("MT5 connection lost.")
                tg.alert_error("Connection", "MT5 disconnected. Reconnecting...")
                if not _reconnect():
                    log.critical("Failed to reconnect after 5 attempts. Exiting.")
                    tg.alert_error("Connection", "MT5 reconnect failed. Bot stopped.")
                    break

            # Run one trading cycle
            trader.run_cycle()

            # Daily summary
            if _should_send_summary():
                trader.send_daily_summary()

            # Sleep until next cycle
            time.sleep(config.LOOP_SLEEP_SEC)

        except KeyboardInterrupt:
            break
        except Exception as e:
            log.error(f"Unexpected error in main loop: {e}", exc_info=True)
            tg.alert_error("Main loop", str(e))
            time.sleep(30)  # brief pause before retry

    log.info("Trader stopped. Disconnecting MT5.")
    disconnect()
    log.info("Done.")


if __name__ == "__main__":
    main()
