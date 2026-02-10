"""
B3_ANCHOR V6A - Live Runner
===========================
Motor B3: Estabilidad Institucional
Estrategia: Golden Cross 4H + Filtro 1D
Activos: BTC, ETH, SOL, LINK, DOT

Ejecutar: py run_b3_demo.py
"""

import asyncio
import logging
import signal
from datetime import datetime
from exchange_connector import ExchangeConnector
from engines.b3_anchor.engine import B3AnchorEngine

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s │ %(name)-12s │ %(levelname)-8s │ %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'b3_demo_{datetime.now().strftime("%Y%m%d")}.log', encoding='utf-8')
    ]
)
logger = logging.getLogger('B3_RUNNER')

async def main():
    logger.info("=" * 60)
    logger.info("⚓ ANTIGRAVITY - B3 ANCHOR V6A RUNNER")
    logger.info("   Institucional Trend (1D/4H) | Sharpe > 2.0 Check")
    logger.info("=" * 60)
    
    # Init Connector (Motor B3)
    # Note: ExchangeConnector needs to support 'B3' config or fallback
    connector = ExchangeConnector(motor='B3', environment='testnet')
    
    # Init Engine
    engine = B3AnchorEngine(connector, environment='testnet')
    
    task = asyncio.create_task(engine.start())
    
    try:
        # Keep alive loop
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("🛑 Señal de parada recibida (KeyboardInterrupt)...")
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}")
    finally:
        logger.info("🛑 Deteniendo motor B3...")
        await engine.stop()
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

if __name__ == "__main__":
    asyncio.run(main())
