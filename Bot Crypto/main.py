import asyncio
import logging
import os
import signal
from dotenv import load_dotenv

# Core
from core.data_feed import DataFeed
from core.state_manager import StateManager
from core.telegram_bot import TelegramInterface
from exchange_connector import ExchangeConnector

# Engines (Adapters)
from engines.b1_sprint.engine import B1SprintEngine
from engines.b2_resilience.engine import B2ResilienceEngine
from engines.b3_anchor.engine import B3AnchorEngine

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('MAIN')

class TrifectaOrchestrator:
    def __init__(self):
        # Load Env
        load_dotenv('.env.testnet') # Local debug, Railway injects envs
        
        self.running = False
        
        # 1. Components
        # Try generic keys, fallback to B1 keys (guaranteed to exist)
        ak = os.getenv('BINANCE_API_KEY') or os.getenv('B1_TESTNET_API_KEY')
        ask = os.getenv('BINANCE_API_SECRET') or os.getenv('B1_TESTNET_API_SECRET')
        
        # Check environment variable for Testnet (default to True if not set, for safety)
        is_testnet = os.getenv('BINANCE_TESTNET', 'true').lower() == 'true'

        self.connector = ExchangeConnector(
            motor='TRIFECTA',
            api_key=ak,
            api_secret=ask,
            testnet=is_testnet
        )
        self.data_feed = DataFeed(testnet=is_testnet)
        self.state_manager = StateManager()
        self.telegram = TelegramInterface(self)
        
        # 2. Kill Switch Globals
        self.initial_capital = 3000.0 # $1000 x 3
        self.current_equity = 3000.0
        self.kill_switch_threshold = 0.85 # -15%
        
        # 3. Engines
        self.b1 = B1SprintEngine(self.connector, 'testnet' if is_testnet else 'production')
        self.b2 = B2ResilienceEngine(self.connector, 'testnet' if is_testnet else 'production')
        self.b3 = B3AnchorEngine(self.connector, 'testnet' if is_testnet else 'production')
        
    async def start(self):
        logger.info(f"🚀 INICIANDO TRIFECTA UNIFICADA (RAILWAY/{'TESTNET' if self.connector.config['is_testnet'] else 'PRODUCTION'})")
        
        # Connect Exchange
        if not self.connector.connect():
            logger.critical("❌ FAILED TO CONNECT TO EXCHANGE. STOPPING.")
            return
        
        # Restore State
        await self._restore_state()
        
        # Start Telegram
        await self.telegram.start()
        
        # Init Engines (Passive Mode Configuration)
        # We need to manually inject configurations if needed or rely on their defaults
        # But importantly, we subscribe them to DataFeed
        
        # Subscribe B1 (5m)
        self.data_feed.add_symbol('SOLUSDT')
        self.data_feed.subscribe_engine(self._dispatch_b1)
        
        # Subscribe B2 (1h) - SOL, AVAX, DOT, ETH
        for sym in ['SOLUSDT', 'AVAXUSDT', 'DOTUSDT', 'ETHUSDT']:
            self.data_feed.add_symbol(sym)
        self.data_feed.subscribe_engine(self._dispatch_b2)
        
        # Subscribe B3 (4h) - BTC, ETH, SOL, LINK, DOT
        for sym in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'LINKUSDT', 'DOTUSDT']:
            self.data_feed.add_symbol(sym)
        self.data_feed.subscribe_engine(self._dispatch_b3)
        
        # Start Data Stream
        self.running = True
        asyncio.create_task(self.data_feed.start())
        
        # Monitor Loop (Equity & Kill Switch)
        await self._monitor_loop()

    async def _monitor_loop(self):
        while self.running:
            try:
                # 1. Check Global Equity
                try:
                    bal = self.connector.get_balance()
                except Exception as bal_err:
                    logger.warning(f"⚠️ Balance check failed (will retry): {bal_err}")
                    bal = None

                if bal:
                    # get_balance() returns: {'total': ..., 'available': ..., 'unrealized_pnl': ...}
                    self.current_equity = float(bal.get('total', 0)) + float(bal.get('unrealized_pnl', 0))
                    
                    # Kill Switch Check (only if we got a real value)
                    if self.current_equity > 0 and self.current_equity < (self.initial_capital * self.kill_switch_threshold):
                        logger.critical(f"🛑 Kill Switch: Equity ${self.current_equity:.2f} < threshold ${self.initial_capital * self.kill_switch_threshold:.2f}")
                        await self.emergency_stop("Global Kill Switch Triggered (-15%)")
                        break
                        
                # 2. Log Status to Supabase every min
                # await self.state_manager.log_heartbeat(...)
                
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                await asyncio.sleep(10)

    async def _dispatch_b1(self, event):
        """Adapter: DataFeed -> B1 Engine Logic"""
        # Event format: {'s': 'SOLUSDT', 'k': {'i': '5m', 'x': True, ...}}
        k = event.get('k', {})
        if k.get('i') == '5m' and k.get('x'): # Closed 5m candle
            # Call B1 processing logic
            # We need to modify B1 engine to expose a 'process_candle' method
            # For now assuming we refactor B1 to have it.
            if hasattr(self.b1, 'on_candle_closed'):
                await self.b1.on_candle_closed(event)

    async def _dispatch_b2(self, event):
        k = event.get('k', {})
        if k.get('i') == '1h' and k.get('x'):
            if hasattr(self.b2, 'on_candle_closed'):
                await self.b2.on_candle_closed(event)

    async def _dispatch_b3(self, event):
        k = event.get('k', {})
        if k.get('i') == '4h' and k.get('x'):
            if hasattr(self.b3, 'on_candle_closed'):
                await self.b3.on_candle_closed(event)

    async def _restore_state(self):
        """Recover from Supabase."""
        state = await self.state_manager.load_active_positions()
        # Apply to engines...
        logger.info("Estado restaurado desde Supabase.")

    async def emergency_stop(self, reason="Unknown"):
        logger.critical(f"🛑 EMERGENCY STOP: {reason}")
        self.running = False
        try:
            await self.data_feed.stop()
        except Exception:
            pass
        try:
            await self.telegram.send_alert(f"🛑 **BOT DETENIDO**: {reason}")
        except Exception:
            pass
        # Don't sys.exit - let the loop end gracefully

    def get_status_report(self):
        b1_state = getattr(self.b1, 'state', 'idle')
        b2_state = getattr(self.b2, 'state', 'idle')
        b3_state = getattr(self.b3, 'state', 'idle')
        return (
            f"**TRIFECTA STATUS**\n"
            f"Equity: ${self.current_equity:.2f}\n"
            f"B1 Sprint: {b1_state}\n"
            f"B2 Resilience: {b2_state}\n"
            f"B3 Anchor: {b3_state}"
        )

if __name__ == "__main__":
    orchestrator = TrifectaOrchestrator()
    loop = asyncio.get_event_loop()
    
    # Graceful Shutdown
    def handle_signal():
        asyncio.create_task(orchestrator.emergency_stop("Manual Shutdown"))
    
    loop.add_signal_handler(signal.SIGINT, handle_signal)
    loop.add_signal_handler(signal.SIGTERM, handle_signal)
    
    loop.run_until_complete(orchestrator.start())
