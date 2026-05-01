"""
MT5 Debug Script — run this first to diagnose the issue
"""
import MetaTrader5 as mt5

# Step 1: Initialize
print("=== Step 1: Initialize ===")
init = mt5.initialize()
print(f"initialize(): {init}")
print(f"last_error(): {mt5.last_error()}")

if not init:
    print("FAILED — MT5 not connected. Is terminal open and logged in?")
    quit()

# Step 2: Terminal info
print("\n=== Step 2: Terminal Info ===")
info = mt5.terminal_info()
print(f"connected : {info.connected}")
print(f"trade_allowed: {info.trade_allowed}")
print(f"name      : {info.name}")

# Step 3: Account info
print("\n=== Step 3: Account Info ===")
acc = mt5.account_info()
if acc:
    print(f"login  : {acc.login}")
    print(f"server : {acc.server}")
    print(f"balance: {acc.balance}")
else:
    print(f"No account info: {mt5.last_error()}")

# Step 4: Test one symbol
print("\n=== Step 4: Test EURUSD ===")
mt5.symbol_select("EURUSD", True)
rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_H1, 0, 10)
if rates is not None:
    print(f"EURUSD H1 bars fetched: {len(rates)}")
    print(f"First bar: {rates[0]}")
else:
    print(f"EURUSD H1 failed: {mt5.last_error()}")

# Step 5: Show first 10 symbols
print("\n=== Step 5: First 10 Symbols ===")
symbols = mt5.symbols_get()
if symbols:
    for s in symbols[:10]:
        print(f"  {s.name:30} visible={s.visible} select={s.select}")
else:
    print(f"No symbols: {mt5.last_error()}")

mt5.shutdown()
print("\nDone.")
