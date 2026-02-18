import os
import sys
import logging
from dotenv import load_dotenv
from exchange_connector import ExchangeConnector
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("CloseTestnet")

def run_close():
    print("=" * 60)
    print("[WARN]  CLOSING ALL OPEN POSITIONS - TESTNET")
    print("=" * 60)
    
    # Load Testnet Env
    env_path = os.path.join(os.path.dirname(__file__), '.env.testnet')
    if os.path.exists(env_path):
        load_dotenv(env_path)
    
    try:
        # Use B1 credentials (guaranteed to represent the account)
        connector = ExchangeConnector(motor='B1', environment='testnet')
        if not connector.connect():
            print("[FAIL] Failed to connect")
            return
        
        # 1. Get Open Positions
        positions = connector.get_open_positions()
        
        if not positions:
            print("[INFO] No open positions found. Account is clean.")
            return

        print(f"[INFO] Found {len(positions)} open positions. Closing now...")
        
        for p in positions:
            symbol = p['symbol']
            amt = float(p.get('quantity', 0))
            side = p['side'] # LONG or SHORT
            leverage = p['leverage']
            pnl = p['pnl']
            
            # Determine correct side to close
            close_side = 'SELL' if side == 'LONG' else 'BUY'
            
            print(f"   -> Closing {symbol} {side} x{leverage} (Qty: {amt}, PnL: ${pnl:.2f})")
            
            try:
                # Attempt to close using 'reduceOnly=True'
                # Try omitting positionSide first (One-Way Mode default)
                # If that fails, try explicit 'LONG'/'SHORT' (Hedge Mode)
                
                # Assume One-Way (likely the blocker)
                try:
                    order = connector.client.futures_create_order(
                        symbol=symbol,
                        side=close_side,
                        type='MARKET',
                        quantity=amt,
                        reduceOnly=True
                    )
                    print(f"     [OK] CLOSED (One-Way): {order['orderId']}")
                    continue # Success
                except Exception as e1:
                    if 'position side' in str(e1).lower():
                        # Try Hedge Mode parameters
                        pos_side = 'LONG' if side == 'LONG' else 'SHORT' # Position to close
                        order = connector.client.futures_create_order(
                            symbol=symbol,
                            side=close_side,
                            positionSide=pos_side,
                            type='MARKET',
                            quantity=amt
                        )
                        print(f"     [OK] CLOSED (Hedge): {order['orderId']}")
                    else:
                        raise e1

            except Exception as e:
                print(f"     [FAIL] FAILED to close {symbol}: {e}")
        
        # Double check
        time.sleep(2)
        remaining = connector.get_open_positions()
        if not remaining:
            print("\n[SUCCESS] All positions successfully closed!")
        else:
            print(f"\n[WARN] {len(remaining)} positions still remain open.")
            
    except Exception as e:
        print(f"[FAIL] Script error: {e}")

if __name__ == "__main__":
    run_close()
