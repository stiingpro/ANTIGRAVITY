"""
B2_RESILIENCE V6 - Live Demo Runner (Dual-Timeframe)
=====================================================
Motor: V6 EMA Crossover Dual-Timeframe
Activos: SOL, AVAX, DOT, ETH (4 pares top)
Timeframe: 1H (ejecución) + 4H (dirección macro)
Leverage: 3x-5x dinámico

Ejecutar: py run_b2_demo.py
Detener: Ctrl+C (cierra posiciones y detiene)
"""

import os
import sys
import time
import signal
import asyncio
import logging
from datetime import datetime
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s │ %(name)-12s │ %(levelname)-8s │ %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            f'b2_demo_{datetime.now().strftime("%Y%m%d")}.log',
            encoding='utf-8'
        )
    ]
)
logger = logging.getLogger('B2_LIVE')

# Cargar credenciales
env_path = os.path.join(os.path.dirname(__file__), '.env.testnet')
load_dotenv(env_path)


# Configuración de precisión por símbolo
SYMBOL_CONFIG = {
    'SOLUSDT':  {'qty_precision': 1, 'price_precision': 2, 'min_qty': 0.1,  'emoji': '☀️'},
    'AVAXUSDT': {'qty_precision': 1, 'price_precision': 3, 'min_qty': 0.1,  'emoji': '🔺'},
    'DOTUSDT':  {'qty_precision': 1, 'price_precision': 3, 'min_qty': 0.1,  'emoji': '⚫'},
    'ETHUSDT':  {'qty_precision': 3, 'price_precision': 2, 'min_qty': 0.001,'emoji': '💎'},
}


class B2DemoRunner:
    """
    Runner del motor B2 V6 en modo Demo continuo.
    4 símbolos | 1H+4H | Estrategia EMA Crossover Dual-TF
    """
    
    def __init__(self):
        self.running = False
        self.connector = None
        self.feed = None
        self.caches = {}  # PriceCache por símbolo
        self.strategy = None
        self.risk_manager = None
        self.kill_switch = None
        
        # Config V6: Top 4 activos
        self.symbols = ['SOLUSDT', 'AVAXUSDT', 'DOTUSDT', 'ETHUSDT']
        
        # Posiciones activas: {symbol: {side, qty, entry, sl, tp}}
        self.active_positions = {}
        
        # Métricas de sesión
        self.session_start = None
        self.trades_executed = 0
        self.signals_generated = 0
        self.signals_rejected = 0
        self.cycle_count = 0
    
    def setup(self) -> bool:
        """Inicializar todos los componentes."""
        logger.info("=" * 60)
        logger.info("🛡️ ANTIGRAVITY HIGH - B2_RESILIENCE V6 DEMO")
        logger.info("   Dual-Timeframe | EMA Cross | 4 Pares")
        logger.info(f"   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)
        
        try:
            # 1. Exchange Connector (Motor B2)
            logger.info("\n📡 Conectando al exchange...")
            from exchange_connector import ExchangeConnector
            self.connector = ExchangeConnector(motor='B2', environment='testnet')
            self.connector.connect()
            
            balance = self.connector.get_balance()
            initial_balance = balance.get('available', 0)
            logger.info(f"💰 Balance: ${initial_balance:.2f} USDT")
            
            # 2. Configurar margen para cada símbolo (leverage 5x max)
            logger.info(f"\n⚙️ Configurando {len(self.symbols)} símbolos (leverage 5x)...")
            for sym in self.symbols:
                try:
                    # Configurar aislado con leverage máximo V6
                    self.connector.client.futures_change_margin_type(
                        symbol=sym, marginType='ISOLATED'
                    )
                except:
                    pass
                try:
                    self.connector.client.futures_change_leverage(
                        symbol=sym, leverage=5
                    )
                    logger.info(f"  ✅ {sym}: ISOLATED 5x")
                except Exception as e:
                    logger.warning(f"  ⚠️ {sym}: {e}")
            
            # 3. Price Cache + datos históricos 1H
            logger.info(f"\n📊 Cargando datos históricos 1H...")
            from data.price_cache import PriceCache
            
            for sym in self.symbols:
                cache = PriceCache(symbol=sym)
                try:
                    klines = self.connector.client.futures_klines(
                        symbol=sym, interval='1h', limit=100
                    )
                    cache.load_historical(klines)
                    self.caches[sym] = cache
                    summary = cache.get_summary()
                    cfg = SYMBOL_CONFIG.get(sym, {})
                    logger.info(
                        f"  {cfg.get('emoji', '•')} {sym}: "
                        f"${summary['price']:,.{cfg.get('price_precision', 2)}f} │ "
                        f"RSI={summary['rsi']:.0f} │ {summary['trend']}"
                    )
                except Exception as e:
                    logger.warning(f"  ⚠️ {sym}: {e}")
            
            # 4. Strategy V6
            logger.info(f"\n📈 Inicializando V6 Dual-TF Strategy...")
            from engines.b2_resilience.strategy import B2Strategy
            from engines.b2_resilience.engine import B2ResilienceEngine
            self.strategy = B2Strategy(B2ResilienceEngine.CONFIG)
            
            # 5. Risk Manager V6
            from engines.b2_resilience.risk_manager import B2RiskManager
            self.risk_manager = B2RiskManager(B2ResilienceEngine.CONFIG)
            self.risk_manager.start_balance = initial_balance
            
            # 6. Kill Switch
            from safety.kill_switch import KillSwitch
            self.kill_switch = KillSwitch(
                max_drawdown_pct=10.0,   # V6: 10% DD
                hibernation_hours=24,
                connector=self.connector
            )
            
            # 7. WebSocket Feed (4 símbolos, 1H)
            logger.info(f"\n🔌 Inicializando WebSocket Feed ({len(self.symbols)} pares)...")
            from data.websocket_feed import BinanceWebSocketFeed
            self.feed = BinanceWebSocketFeed(
                environment='testnet',
                symbols=self.symbols,
                timeframe='1h'
            )
            
            self.feed.on_ticker(self._on_price_update)
            self.feed.on_kline(self._on_kline_update)
            
            logger.info("\n✅ Todos los componentes V6 inicializados")
            logger.info(f"   Estrategia: EMA 20/50 (1H) + EMA 200 (4H)")
            logger.info(f"   SL: 2.0x ATR(4H) │ TP: 4.0x ATR(4H)")
            logger.info(f"   Leverage: 3x-5x dinámico")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error en setup: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _on_price_update(self, ticker_data):
        """Precio actualizado via WebSocket."""
        symbol = ticker_data.get('symbol', '')
        if symbol in self.caches:
            self.caches[symbol].update_price(float(ticker_data.get('price', 0)))
    
    def _on_kline_update(self, kline_data):
        """Kline actualizada via WebSocket (1H)."""
        symbol = kline_data.get('symbol', '')
        is_closed = kline_data.get('is_closed', False)
        
        if symbol in self.caches:
            self.caches[symbol].update_kline(kline_data)
            
            if is_closed:
                logger.info(
                    f"  🕐 {symbol} vela 1H cerrada │ "
                    f"Close=${float(kline_data.get('close', 0)):,.2f}"
                )
    
    async def run(self):
        """Loop principal de trading."""
        self.running = True
        self.session_start = datetime.now()
        
        # Iniciar WebSocket en background
        ws_task = asyncio.create_task(self.feed.start())
        await asyncio.sleep(3)
        
        logger.info("\n" + "=" * 60)
        logger.info("🏁 B2_RESILIENCE V6 EN VIVO │ 4 Pares │ 1H+4H │ Dual-TF")
        logger.info("   Ctrl+C para detener")
        logger.info("=" * 60)
        
        try:
            while self.running:
                self.cycle_count += 1
                
                try:
                    await self._trading_cycle()
                except Exception as e:
                    logger.error(f"❌ Error en ciclo #{self.cycle_count}: {e}")
                
                # Cada 60 segundos
                for _ in range(60):
                    if not self.running:
                        break
                    await asyncio.sleep(1)
                    
        except asyncio.CancelledError:
            pass
        finally:
            self.feed.running = False
            try:
                ws_task.cancel()
                await asyncio.wait_for(ws_task, timeout=2)
            except:
                pass
    
    async def _trading_cycle(self):
        """Un ciclo de análisis multi-símbolo dual-timeframe."""
        # 1. Balance actual
        balance_data = self.connector.get_balance()
        current_balance = balance_data.get('total', 0)
        
        # 2. Kill Switch check
        if self.kill_switch.check_trigger(
            self.risk_manager.start_balance, current_balance
        ):
            logger.critical("🚨 KILL SWITCH ACTIVADO — 10% DD")
            self.running = False
            return
        
        # 3. Obtener posiciones del exchange
        open_positions = self.connector.get_open_positions()
        active_pos = {
            p['symbol']: p for p in open_positions 
            if float(p.get('positionAmt', 0)) != 0
        }
        
        total_active = len(active_pos)
        
        # 4. Dashboard periódico
        if self.cycle_count % 2 == 0:
            pnl = current_balance - self.risk_manager.start_balance
            pnl_pct = (pnl / self.risk_manager.start_balance * 100) if self.risk_manager.start_balance > 0 else 0
            elapsed = datetime.now() - self.session_start
            
            logger.info(
                f"{'─'*60}\n"
                f"  🛡️ Ciclo #{self.cycle_count} │ ⏱️{str(elapsed).split('.')[0]} │ "
                f"Pos={total_active}/4 │ Trades={self.trades_executed} │ "
                f"PnL=${pnl:+.2f} ({pnl_pct:+.2f}%)"
            )
            
            # Precios de cada símbolo
            lines = []
            for sym in self.symbols:
                cache = self.caches.get(sym)
                if cache and cache.last_price > 0:
                    cfg = SYMBOL_CONFIG.get(sym, {})
                    ind = cache.indicators
                    pos_mark = "📍" if sym in active_pos else "  "
                    lines.append(
                        f"  {pos_mark} {cfg.get('emoji', '•')} {sym:10s} "
                        f"${cache.last_price:>12,.{cfg.get('price_precision', 2)}f} │ "
                        f"RSI={ind.rsi_14:5.1f} │ {ind.trend:8s} │ "
                        f"MACD={'↑' if ind.macd_histogram > 0 else '↓'}"
                    )
            if lines:
                logger.info("\n".join(lines))
            logger.info(f"{'─'*60}")
        
        # 5. Analizar cada símbolo (dual-timeframe)
        for sym in self.symbols:
            # Skip si ya tiene posición
            if sym in active_pos:
                continue
            
            # Skip si max posiciones alcanzado (4)
            if total_active >= 4:
                break
            
            cache = self.caches.get(sym)
            if not cache or len(cache.candles) < 55:
                continue
            
            # Risk manager check
            class _FakeSignal:
                symbol = sym
            if not self.risk_manager.can_trade(_FakeSignal()):
                continue
            
            # Generar market_data 1H (desde cache)
            market_data_1h = cache.get_market_data()
            market_data_1h['symbol'] = sym
            market_data_1h['timeframe'] = '1h'
            
            # Obtener datos 4H directamente del exchange
            try:
                klines_4h = self.connector.client.futures_klines(
                    symbol=sym, interval='4h', limit=220
                )
                market_data_4h = {
                    'symbol': sym,
                    'price': cache.last_price,
                    'klines': klines_4h,
                    'timeframe': '4h'
                }
            except Exception as e:
                logger.warning(f"  ⚠️ Error datos 4H {sym}: {e}")
                continue
            
            # Analizar con estrategia V6 dual-timeframe
            signal = self.strategy.analyze(market_data_1h, market_data_4h)
            
            if signal:
                self.signals_generated += 1
                cfg = SYMBOL_CONFIG.get(sym, {})
                pp = cfg.get('price_precision', 2)
                
                logger.info(
                    f"📈 SEÑAL V6 {cfg.get('emoji', '')} {signal.side.value} {sym} │ "
                    f"Fuerza={signal.strength:.2f} │ Lev={signal.leverage}x │ "
                    f"Entry=${signal.entry_price:,.{pp}f} │ "
                    f"SL=${signal.stop_loss:,.{pp}f} │ "
                    f"TP=${signal.take_profit:,.{pp}f} │ "
                    f"{signal.reason}"
                )
                
                # Ejecutar
                await self._execute_signal(signal, current_balance)
                total_active += 1
    
    async def _execute_signal(self, signal, current_balance):
        """Ejecutar una señal de trading V6 (Hedge mode)."""
        from engines.b2_resilience.engine import TradeSide
        
        sym = signal.symbol
        cfg = SYMBOL_CONFIG.get(sym, {})
        qty_prec = cfg.get('qty_precision', 1)
        pp = cfg.get('price_precision', 2)
        min_qty = cfg.get('min_qty', 0.1)
        
        # Hedge mode
        pos_side = 'LONG' if signal.side == TradeSide.LONG else 'SHORT'
        sl_side = 'SELL' if signal.side == TradeSide.LONG else 'BUY'
        
        try:
            # Calcular tamaño: 3% del balance × leverage dinámico
            margin = current_balance * 0.03  # 3%
            leverage = signal.leverage        # 3x-5x dinámico
            notional = margin * leverage
            
            if signal.entry_price <= 0:
                logger.warning(f"  ⚠️ Precio 0 en {sym} (testnet) — Saltando")
                return
            
            quantity = notional / signal.entry_price
            
            # Ajustar leverage en exchange
            try:
                self.connector.client.futures_change_leverage(
                    symbol=sym, leverage=leverage
                )
            except:
                pass
            
            # Aplicar precisión del símbolo
            quantity = round(quantity, qty_prec)
            if qty_prec == 0:
                quantity = int(quantity)
            if quantity < min_qty:
                quantity = min_qty
            
            logger.info(
                f"🎯 EJECUTANDO: {signal.side.value} {quantity} {sym} "
                f"(positionSide={pos_side}, leverage={leverage}x)"
            )
            
            # 1. Orden de mercado (Hedge mode)
            order = self.connector.client.futures_create_order(
                symbol=sym,
                side=signal.side.value,
                positionSide=pos_side,
                type='MARKET',
                quantity=quantity
            )
            
            order_id = order['orderId']
            logger.info(f"  ✅ Orden #{order_id} ejecutada")
            
            # 2. Stop Loss (Hedge mode)
            self.connector.client.futures_create_order(
                symbol=sym,
                side=sl_side,
                positionSide=pos_side,
                type='STOP_MARKET',
                stopPrice=round(signal.stop_loss, pp),
                closePosition=True
            )
            logger.info(f"  🛑 SL: ${signal.stop_loss:,.{pp}f}")
            
            # 3. Take Profit (Hedge mode)
            self.connector.client.futures_create_order(
                symbol=sym,
                side=sl_side,
                positionSide=pos_side,
                type='TAKE_PROFIT_MARKET',
                stopPrice=round(signal.take_profit, pp),
                closePosition=True
            )
            logger.info(f"  🎯 TP: ${signal.take_profit:,.{pp}f}")
            
            self.trades_executed += 1
            self.risk_manager.on_trade_opened(signal)
            
            rr = (abs(signal.take_profit - signal.entry_price) / 
                  abs(signal.entry_price - signal.stop_loss)
                  if abs(signal.entry_price - signal.stop_loss) > 0 else 0)
            
            logger.info(
                f"  📊 Trade #{self.trades_executed} │ "
                f"{signal.side.value} {quantity} {sym} │ "
                f"Lev={leverage}x │ R/R={rr:.1f}:1"
            )
            
        except Exception as e:
            logger.error(f"  ❌ Error ejecutando {sym}: {e}")
    
    async def shutdown(self):
        """Shutdown graceful."""
        logger.info("\n" + "=" * 60)
        logger.info("🛑 CERRANDO B2_RESILIENCE V6...")
        logger.info("=" * 60)
        
        self.running = False
        
        # Cerrar posiciones y órdenes
        try:
            positions = self.connector.get_open_positions()
            active = [p for p in positions if float(p.get('positionAmt', 0)) != 0]
            
            if active:
                logger.info(f"📍 Cerrando {len(active)} posiciones...")
                for pos in active:
                    symbol = pos['symbol']
                    amount = float(pos['positionAmt'])
                    close_side = 'SELL' if amount > 0 else 'BUY'
                    pos_side = 'LONG' if amount > 0 else 'SHORT'
                    
                    self.connector.client.futures_create_order(
                        symbol=symbol,
                        side=close_side,
                        positionSide=pos_side,
                        type='MARKET',
                        quantity=abs(amount)
                    )
                    logger.info(f"  ✅ {symbol} cerrada ({amount})")
                
                # Cancelar órdenes pendientes
                for sym in self.symbols:
                    try:
                        self.connector.client.futures_cancel_all_open_orders(symbol=sym)
                    except:
                        pass
                logger.info("  ✅ Órdenes pendientes canceladas")
            else:
                logger.info("📍 Sin posiciones abiertas")
                
        except Exception as e:
            logger.error(f"Error en shutdown: {e}")
        
        # Resumen
        elapsed = datetime.now() - self.session_start if self.session_start else None
        balance = self.connector.get_balance()
        final_balance = balance.get('total', 0)
        pnl = final_balance - self.risk_manager.start_balance
        
        logger.info("\n" + "=" * 60)
        logger.info("📋 RESUMEN DE SESIÓN B2 V6")
        logger.info("=" * 60)
        logger.info(f"  ⏱️ Duración:        {str(elapsed).split('.')[0] if elapsed else 'N/A'}")
        logger.info(f"  🔄 Ciclos:          {self.cycle_count}")
        logger.info(f"  📈 Señales:         {self.signals_generated}")
        logger.info(f"  🛡️ Rechazadas:      {self.signals_rejected}")
        logger.info(f"  💹 Trades:          {self.trades_executed}")
        logger.info(f"  💰 Balance final:   ${final_balance:.2f}")
        logger.info(f"  📊 PnL:             ${pnl:+.2f}")
        logger.info("=" * 60)


async def main():
    runner = B2DemoRunner()
    
    if not runner.setup():
        logger.error("❌ Setup falló. Abortando.")
        return 1
    
    def handle_shutdown(sig, frame):
        logger.info("\n⚡ Ctrl+C detectado - Cerrando...")
        runner.running = False
    
    signal.signal(signal.SIGINT, handle_shutdown)
    
    try:
        await runner.run()
    finally:
        await runner.shutdown()
    
    return 0


if __name__ == '__main__':
    result = asyncio.run(main())
    sys.exit(result)
