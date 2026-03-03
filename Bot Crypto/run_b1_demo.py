"""
B1_SPRINT V5.1 - Live Runner (SOL Only)
=======================================
Ejecuta el motor B1 V5.1 en modo demostración/testnet.
Activo: SOLUSDT
Estrategia: 5m EMA/VWAP Execution + 15m Trend Confirmation
Seguridad: Kill-Switch (-15%)
Webhook: Escucha en puerto 8080 para señales TradingView

Ejecutar: py run_b1_demo.py
"""

import asyncio
import logging
import os
import signal
from datetime import datetime
from dotenv import load_dotenv
from exchange_connector import ExchangeConnector
from engines.b1_sprint.engine import B1SprintEngine
from core.webhook_server import WebhookServer
from core.telegram_bot import TelegramInterface

# Cargar variables de entorno
load_dotenv('.env.testnet')

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


class B1DemoOrchestrator:
    """Shim orquestador para modo demo con Webhook + Telegram."""
    
    def __init__(self, connector, engine):
        self.connector = connector
        self.b1 = engine
        self.b2 = None
        self.b3 = None
        self.telegram = TelegramInterface(self)
        self.webhook = WebhookServer(self)
    
    def get_status_report(self):
        state = self.b1.state.value if hasattr(self.b1.state, 'value') else str(self.b1.state)
        return (
            f"**B1 DEMO STATUS**\n"
            f"B1 Sprint: {state}\n"
            f"Mode: Standalone + Webhook"
        )


async def main():
    logger.info("=" * 60)
    logger.info("🚀 ANTIGRAVITY - B1 V5.1 SPRINT RUNNER")
    logger.info("   SOLUSDT | 5m/15m Hybrid | Kill-Switch Active")
    logger.info("   Webhook: puerto 8080 | Telegram: Activo")
    logger.info("=" * 60)
    
    # Init Connector
    connector = ExchangeConnector(motor='B1', environment='testnet')
    if not connector.connect():
        logger.error("Fallo al conectar con Exchange")
        return
    
    # Init Engine
    engine = B1SprintEngine(connector, environment='testnet')
    
    # Init Orchestrator Shim (Webhook + Telegram)
    orchestrator = B1DemoOrchestrator(connector, engine)
    
    task = None
    try:
        # Start Telegram
        await orchestrator.telegram.start()
        
        # Start Webhook Server
        port = int(os.getenv('PORT', 8080))
        await orchestrator.webhook.start(port=port)
        logger.info(f"🌍 Webhook activo en http://0.0.0.0:{port}/webhook")
        
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
        await orchestrator.webhook.stop()
        logger.info("🛑 Deteniendo motor...")
        await engine.stop()
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

if __name__ == "__main__":
    asyncio.run(main())

