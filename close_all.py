import os
import sys
import logging
import math
from dotenv import load_dotenv

# Path setup
current_dir = os.getcwd()
bot_crypto_path = os.path.join(current_dir, 'Bot Crypto')
if os.path.exists(bot_crypto_path):
    sys.path.append(bot_crypto_path)
else:
    sys.path.append(current_dir)

from exchange_connector import ExchangeConnector

# logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("CleanUp")

def close_all():
    logger.info("🚀 Starting CleanUp sequence...")
    
    # Initialize connector
    connector = ExchangeConnector(motor='TRIFECTA', environment='testnet')
    if not connector.connect():
        logger.error("❌ Connection failed.")
        return

    # 1. Fetch positions
    positions = connector.get_open_positions()
    
    if not positions:
        logger.info("ℹ️ No open positions to close.")
    else:
        logger.info(f"📊 Found {len(positions)} open positions. Closing now...")
        
        for pos in positions:
            symbol = pos['symbol']
            side = pos['side']
            qty = pos['quantity']
            
            # Close params
            close_side = 'SELL' if side == 'LONG' else 'BUY'
            pos_side = side 
            
            logger.info(f"🛠 Processing {symbol} ({side})...")
            try:
                # Cancel open SL/TP
                connector.client.futures_cancel_all_open_orders(symbol=symbol)
                logger.info(f"   🗑 Open orders cancelled.")
                
                # Execute Market Close
                order = connector.client.futures_create_order(
                    symbol=symbol,
                    side=close_side,
                    positionSide=pos_side,
                    type='MARKET',
                    quantity=qty
                )
                logger.info(f"   ✅ Position closed: OrderID {order.get('orderId')}")
            except Exception as e:
                logger.error(f"   ❌ Failed to close {symbol}: {e}")

    # 2. Final verification
    logger.info("🔍 Finalizing verification...")
    final_check = connector.get_open_positions()
    if not final_check:
        logger.info("✨ SUCCESS: All positions and orders cleaned on Binance Demo.")
        print("CLEANUP_OK")
    else:
        logger.warning(f"⚠️ Verification: {len(final_check)} positions still open.")

if __name__ == "__main__":
    close_all()
