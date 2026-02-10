
import asyncio
import logging
from exchange_connector import ExchangeConnector

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('ORPHAN_CLOSER')

ORPHANS = ['BTCUSDT', 'XRPUSDT']

async def close_orphans():
    logger.info("🔪 Iniciando script de cierre de huérfanos...")
    connector = ExchangeConnector(motor='B1', environment='testnet')
    connector.connect()
    
    positions = connector.get_open_positions()
    active_orphans = [p for p in positions if p['symbol'] in ORPHANS]
    
    if not active_orphans:
        logger.info("✅ No se encontraron posiciones huérfanas activas.")
        return

    logger.info(f"🚨 Encontradas {len(active_orphans)} posiciones huérfanas: {[p['symbol'] for p in active_orphans]}")
    
    for pos in active_orphans:
        symbol = pos['symbol']
        quantity = pos['quantity']
        pos_side = pos['side'] # 'LONG' or 'SHORT'
        
        # Close logic: Long -> Sell, Short -> Buy
        side = 'SELL' if pos_side == 'LONG' else 'BUY'
        
        logger.info(f"🔻 Cerrando {symbol} ({quantity} {pos_side})...")
        try:
            connector.client.futures_create_order(
                symbol=symbol,
                side=side,
                positionSide=pos_side,
                type='MARKET',
                quantity=quantity
            )
            logger.info(f"  ✅ {symbol} CERRADA exitosamente.")
        except Exception as e:
            logger.error(f"  ❌ Error cerrando {symbol}: {e}")

    logger.info("🏁 Operación completada.")

if __name__ == "__main__":
    asyncio.run(close_orphans())
