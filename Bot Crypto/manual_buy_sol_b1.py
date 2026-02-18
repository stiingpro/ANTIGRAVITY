"""
Manual Buy SOL (B1 Testnet)
===========================
Executes a MARKET BUY order for ~20 USDT of SOL on Binance Testnet using B1 credentials.
"""
import logging
import math
from exchange_connector import ExchangeConnector

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('ManualBuy')

def main():
    logger.info("🚀 Initiating Manual Buy for B1 (SOLUSDT)...")
    
    # 1. Initialize Connector
    connector = ExchangeConnector(motor='B1', environment='testnet')
    if not connector.connect():
        logger.error("❌ Failed to connect.")
        return

    symbol = 'SOLUSDT'
    target_usdt = 20.0
    
    try:
        # 2. Get Current Price
        ticker = connector.client.futures_symbol_ticker(symbol=symbol)
        price = float(ticker['price'])
        logger.info(f"💰 Current {symbol} Price: ${price:.2f}")
        
        # 3. Calculate Quantity
        # Precision for SOL is usually 0 decimals or 1 decimal depending on config, checking exchange info is better but let's try 1 decimal
        # Ideally we fetch exchange info.
        exchange_info = connector.client.futures_exchange_info()
        symbol_info = next((s for s in exchange_info['symbols'] if s['symbol'] == symbol), None)
        precision = 0
        if symbol_info:
            precision = symbol_info['quantityPrecision']
            logger.info(f"📏 Quantity Precision for {symbol}: {precision}")
            
        raw_qty = target_usdt / price
        quantity = round(raw_qty, precision)
        
        logger.info(f"🛒 Calculating quantity: {target_usdt} USDT / {price} = {raw_qty:.4f} => {quantity}")
        
        if quantity <= 0:
            logger.error("❌ Quantity too small.")
            return

        # 4. Execute Order (Hedge Mode: positionSide='LONG')
        logger.info(f"👉 Placing BUY Order for {quantity} {symbol}...")
        order = connector.client.futures_create_order(
            symbol=symbol,
            side='BUY',
            positionSide='LONG',
            type='MARKET',
            quantity=quantity
        )
        
        logger.info("✅ Order Successful!")
        logger.info(f"   Order ID: {order['orderId']}")
        logger.info(f"   Status: {order['status']}")
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
