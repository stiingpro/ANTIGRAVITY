import os
import sys
import logging
from dotenv import load_dotenv
from exchange_connector import ExchangeConnector

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("ManualCheckTestnet")

def run_check():
    print("=" * 60)
    print("MANUAL CONNECTIVITY CHECK - TESTNET (B1, B2, B3)")
    print("=" * 60)
    
    # Load Testnet Env
    env_path = os.path.join(os.path.dirname(__file__), '.env.testnet')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print(f"Loaded {env_path}")
    else:
        print(f"[WARN] .env.testnet not found at {env_path}, relying on system env vars")

    motors = ['B1', 'B2', 'B3']
    
    for motor in motors:
        print(f"\n{'='*20} Checking {motor} (TESTNET) {'='*20}")
        try:
            # Force environment='testnet'
            connector = ExchangeConnector(motor=motor, environment='testnet')
            if not connector.connect():
                print(f"[FAIL] Failed to connect {motor}")
                continue
            
            # 1. Check Balance
            try:
                balance = connector.get_balance()
                total = balance.get('total', 0)
                print(f"[INFO] Balance: ${total:.2f} USDT")
            except Exception as e:
                print(f"[FAIL] Failed to get balance: {e}")
                continue

            # 2. Check Permissions (Configure Margin)
            print("[INFO] Checking Permissions (Configure Margin)...")
            try:
                connector.configure_margin('BTCUSDT')
                print("[PASS] Permissions OK")
            except Exception as e:
                 print(f"[WARN] Configuration Issue (likely active positions): {e}")
            
            # 2.5 Check Open Positions
            try:
                positions = connector.get_open_positions()
                print(f"[INFO] Open Positions: {len(positions)}")
                for p in positions:
                    print(f"   - {p['symbol']} {p['side']} x{p['leverage']} (PnL: ${p['pnl']:.2f})")
            except Exception as e:
                print(f"[FAIL] Failed to list positions: {e}")

            # 3. Force Operation (Limit Order Test)
            print(f"[INFO] Executing FORCED OPERATION (Limit Buy BTCUSDT)...")
            try:
                # Get current price
                ticker = connector.client.futures_symbol_ticker(symbol='BTCUSDT')
                current_price = float(ticker['price'])
                print(f"   Current BTC Price: ${current_price:.2f}")
                
                # Set limit price at -50% (Safe for testing)
                limit_price = int(current_price * 0.5)
                
                # Calculate quantity for ~200 USDT value (Testnet Min Notional is high, use enough buffer)
                # qty * limit_price = 200
                target_value = 200.0
                raw_qty = target_value / limit_price
                # Round to 3 decimals
                qty = round(raw_qty, 3)
                if qty == 0: qty = 0.005
                
                print(f"   Placing LIMIT BUY: {qty} BTC @ ${limit_price} (Val: ${qty*limit_price:.2f})")
                
                # Place far out of money limit order
                order = connector.client.futures_create_order(
                    symbol='BTCUSDT',
                    side='BUY',
                    positionSide='LONG',
                    type='LIMIT',
                    timeInForce='GTC',
                    quantity=qty, 
                    price=str(limit_price)
                )
                print(f"   [PASS] Order Placed: {order['orderId']} (Status: {order['status']})")
                
                # Cancel immediately
                cancel = connector.client.futures_cancel_order(symbol='BTCUSDT', orderId=order['orderId'])
                print(f"   [PASS] Order Cancelled: {cancel['orderId']}")
                
            except Exception as e:
                print(f"   [FAIL] FORCED OPERATION FAILED: {e}")
                
        except Exception as e:
            print(f"[FAIL] Error checking {motor}: {e}")

if __name__ == "__main__":
    run_check()
