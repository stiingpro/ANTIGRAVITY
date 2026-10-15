import asyncio
import logging
import os
import signal
from dotenv import load_dotenv

# Core
from core.data_feed import DataFeed
from core.state_manager import StateManager
from core.telegram_bot import TelegramInterface
from core.webhook_server import WebhookServer
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
        self.webhook = WebhookServer(self) # New Webhook Component
        
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
        
        # Start Webhook Server (Port 8080 or PORT env)
        port = int(os.getenv('PORT', 8080))
        await self.webhook.start(port=port)
        
        # Init Engines (Passive Mode Configuration)
        # We need to manually inject configurations if needed or rely on their defaults
        # But importantly, we subscribe them to DataFeed
        
        # Initialize Engines
        await self.b1.initialize()
        await self.b2.initialize()
        await self.b3.initialize()

        # Subscribe B1 (5m)
        for sym in self.b1.CONFIG.get('symbols', ['SOLUSDT']):
            self.data_feed.add_symbol(sym)
        self.data_feed.subscribe_engine(self._dispatch_b1)
        
        # Subscribe B2 (1h) - ETH, AVAX, DOT
        for sym in self.b2.CONFIG.get('symbols', ['ETHUSDT', 'AVAXUSDT', 'DOTUSDT']):
            self.data_feed.add_symbol(sym)
        self.data_feed.subscribe_engine(self._dispatch_b2)
        
        # Subscribe B3 (4h) - BTC, PAXG, LINK
        for sym in self.b3.CONFIG.get('symbols', ['BTCUSDT', 'PAXGUSDT', 'LINKUSDT']):
            self.data_feed.add_symbol(sym)
        self.data_feed.subscribe_engine(self._dispatch_b3)
        
        # Start Data Stream
        self.running = True
        asyncio.create_task(self.data_feed.start())
        asyncio.create_task(self._v8_scan_loop())
        
        # Monitor Loop (Equity & Kill Switch)
        await self._monitor_loop()

    async def _v8_scan_loop(self):
        """Escaneo autónomo cada 5 minutos de los 17 activos V8 (B1, B2 y B3) 24/7 en Railway/Local."""
        import demo_trifecta_2026 as demo
        while self.running:
            try:
                state = demo.load_state()
                await asyncio.to_thread(demo.run_live_scan, state)
            except Exception as e:
                logger.warning(f"⚠️ V8 scan loop warning: {e}")
            await asyncio.sleep(300)

    async def _monitor_loop(self):
        while self.running:
            try:
                # 1. Check Global Equity (non-blocking via asyncio.to_thread)
                try:
                    bal = await asyncio.to_thread(self.connector.get_balance)
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
        """Recover active positions from Supabase into B1, B2, and B3."""
        try:
            state = await self.state_manager.load_active_positions()
            if not state:
                logger.info("ℹ️ Sin estado previo en Supabase (se usará sync directo de Binance).")
                return
            from datetime import datetime
            from engines.b1_sprint.engine import Position as B1Position, TradeSide as B1Side
            from engines.b2_resilience.engine import Position as B2Position, TradeSide as B2Side

            restored_count = 0
            # Restore B1
            for sym, pdata in state.get(self.b1.CONFIG['motor_id'], {}).items():
                side_str = pdata.get('side', 'LONG')
                self.b1.position_manager.active_positions[sym] = B1Position(
                    symbol=sym,
                    side=B1Side.LONG if side_str in ('LONG', 'BUY') else B1Side.SHORT,
                    entry_price=float(pdata.get('entry_price', 0)),
                    quantity=float(pdata.get('quantity', 0)),
                    stop_loss=float(pdata.get('stop_loss', 0)),
                    take_profit=float(pdata.get('take_profit', 0)),
                    opened_at=datetime.now(),
                    sl_order_id=pdata.get('sl_order_id'),
                    tp_order_id=pdata.get('tp_order_id'),
                )
                restored_count += 1

            # Restore B2
            for sym, pdata in state.get(self.b2.CONFIG['motor_id'], {}).items():
                side_str = pdata.get('side', 'LONG')
                self.b2.position_manager.add_position(B2Position(
                    symbol=sym,
                    side=B2Side.LONG if side_str in ('LONG', 'BUY') else B2Side.SHORT,
                    entry_price=float(pdata.get('entry_price', 0)),
                    quantity=float(pdata.get('quantity', 0)),
                    stop_loss=float(pdata.get('stop_loss', 0)),
                    take_profit=float(pdata.get('take_profit', 0)),
                    leverage=int(pdata.get('leverage', 3)),
                    opened_at=datetime.now(),
                ))
                restored_count += 1

            # Restore B3
            for sym, pdata in state.get(self.b3.CONFIG['motor_id'], {}).items():
                self.b3.active_positions[sym] = pdata
                restored_count += 1

            logger.info(f"✅ Estado restaurado desde Supabase ({restored_count} posiciones).")
        except Exception as e:
            logger.warning(f"⚠️ Error restaurando estado desde Supabase: {e}")

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
        # Helper to get state string safely
        def get_state_str(engine, default='stopped'):
            if hasattr(engine, 'state'):
                s = engine.state
                return s.value if hasattr(s, 'value') else str(s)
            elif hasattr(engine, 'running'):
                return 'running' if engine.running else 'stopped'
            return default

        b1_state = get_state_str(self.b1)
        b2_state = get_state_str(self.b2)
        b3_state = get_state_str(self.b3)
        
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
    
    try:
        loop.add_signal_handler(signal.SIGINT, handle_signal)
        loop.add_signal_handler(signal.SIGTERM, handle_signal)
    except NotImplementedError:
        logger.warning("⚠️ Signal handlers not supported on this platform (Windows?) - Use Ctrl+C to stop.")
    
    loop.run_until_complete(orchestrator.start())
