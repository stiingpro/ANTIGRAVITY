"""
B1_SPRINT V5.1 - Live Runner (SOL Only)
=======================================
Ejecuta el motor B1 V5.1 en modo demostración/testnet.
Activo: SOLUSDT
Estrategia: 5m EMA/VWAP Execution + 15m Trend Confirmation
Seguridad: Kill-Switch (-15%)

Ejecutar: py run_b1_demo.py
"""

import asyncio
import logging
import signal
from datetime import datetime
from exchange_connector import ExchangeConnector
from engines.b1_sprint.engine import B1SprintEngine

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s │ %(name)-12s │ %(levelname)-8s │ %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'b1_v51_demo_{datetime.now().strftime("%Y%m%d")}.log', encoding='utf-8')
    ]
)
logger = logging.getLogger('B1_RUNNER')

async def main():
    logger.info("=" * 60)
    logger.info("🚀 ANTIGRAVITY - B1 V5.1 SPRINT RUNNER")
    logger.info("   SOLUSDT | 5m/15m Hybrid | Kill-Switch Active")
    logger.info("=" * 60)
    
    # Init Connector
    connector = ExchangeConnector(motor='B1', environment='testnet')
    if not connector.connect():
        logger.error("Fallo al conectar con Exchange")
        return
    
    # Init Engine
    engine = B1SprintEngine(connector, environment='testnet')
    
    try:
        # Start Engine
        task = asyncio.create_task(engine.start())
        
        # Keep alive loop
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("🛑 Señal de parada recibida (KeyboardInterrupt)...")
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}")
    finally:
        # Stop Engine
        logger.info("🛑 Deteniendo motor...")
        await engine.stop()
        # Cancel task if running
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

if __name__ == "__main__":
    asyncio.run(main())
