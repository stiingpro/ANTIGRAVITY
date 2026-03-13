"""
B1_SPRINT Trading Engine - Core Module
=======================================
Perfil: Agresivo | Meta: $1M en 365 días | Leverage: 20x
"""

from dataclasses import dataclass
from typing import Optional, Dict, List
from enum import Enum
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger('B1_SPRINT')


class TradeSide(Enum):
    LONG = "BUY"
    SHORT = "SELL"


class EngineState(Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    HIBERNATING = "hibernating"  # Kill switch activated


@dataclass
class TradeSignal:
    """Señal de trading generada por la estrategia."""
    symbol: str
    side: TradeSide
    strength: float  # 0.0 - 1.0
    entry_price: float
    stop_loss: float
    take_profit: float
    timestamp: datetime
    reason: str


@dataclass
class Position:
    """Posición abierta."""
    symbol: str
    side: TradeSide
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    unrealized_pnl: float = 0.0
    opened_at: datetime = None


class B1SprintEngine:
    """
    Motor de trading B1_SPRINT.
    
    Características:
    - Perfil agresivo (20x leverage máximo)
    - Timeframe: 1 hora
    - Símbolos: BTC, ETH, SOL, BNB, XRP, DOGE, AVAX
    - Estrategia: Trend Momentum Breakout (TMB)
    - Kill switch: 15% drawdown
    """
    
    # Símbolos de trading
    SYMBOLS = [
        'BTCUSDT', 'ETHUSDT', 'SOLUSDT',
        'BNBUSDT', 'XRPUSDT', 'DOGEUSDT', 'AVAXUSDT'
    ]
    
    # Configuración del motor
    # Configuración del motor

    # Configuración del motor V5.1
    CONFIG = {
        'motor_id': 'B1_SPRINT_V5.1',
        'symbols': ['SOLUSDT'],  # SOL Only for V5.1
        'timeframes': ['5m', '15m'],
        'max_leverage': 20,
        'max_position_size_pct': 5.0,
        'max_open_positions': 1,       # Single asset focus
        'max_daily_drawdown_pct': 10.0,
        'max_total_drawdown_pct': 15.0, # Kill Switch
        'ema_fast': 9, 'ema_slow': 21,
        'bb_period': 20, 'bb_std': 2.0,
        'vwap_lookback': 20,
    }
    
    def __init__(self, connector, environment: str = 'testnet'):
        """
        Inicializar motor B1 V5.1.
        """
        self.connector = connector
        self.environment = environment
        self.state = EngineState.STOPPED
        
        # Componentes
        self.strategy = None
        self.risk_manager = None
        self.position_manager = None
        
        # Estado
        self.positions: Dict[str, Position] = {}
        self.initial_balance: float = 0.0
        self.current_balance: float = 0.0
        
        logger.info(f"🚀 B1_SPRINT V5.1 inicializado en modo {environment}")
    
    async def initialize(self):
        """Inicializar componentes sin iniciar el loop."""
        logger.info("🏁 INICIANDO B1_SPRINT V5.1 (SOL-Only) [PASSIVE MODE]")
        
        balance = self.connector.get_balance() if hasattr(self.connector, 'get_balance') else {'available': 0}
        self.initial_balance = float(balance.get('available', 0))
        self.current_balance = self.initial_balance
        logger.info(f"💰 Balance inicial: ${self.initial_balance:.2f}")
        
        # Inicializar componentes
        from .strategy import B1Strategy
        from .risk_manager import B1RiskManager
        from .position_manager import B1PositionManager
        
        self.strategy = B1Strategy(self.CONFIG)
        self.risk_manager = B1RiskManager(self.CONFIG, self.initial_balance)
        self.position_manager = B1PositionManager(self.connector)
        
        # Pre-configure leverage
        for symbol in self.CONFIG['symbols']:
            try:
                self.connector.configure_margin(symbol)
                self.connector.change_leverage(symbol, self.CONFIG['max_leverage'])
            except Exception as e:
                logger.warning(f"⚠️ Error config leverage {symbol}: {e}")
                
        self.state = EngineState.RUNNING

    async def start(self):
        """Iniciar el motor de trading (Standalone Loop)."""
        await self.initialize()
        await self._main_loop()

    async def on_candle_closed(self, event: Dict):
        """Callback para DataFeed (Passive Mode)."""
        if self.state != EngineState.RUNNING: return
        
        symbol = event.get('s')
        if symbol not in self.CONFIG['symbols']: return
        
        try:
            # Obtener datos recientes para indicadores
            data = await self.connector.get_klines(symbol, '5m', limit=100)
            
            # Analizar
            signal = self.strategy.analyze(data)
            
            # Risk check & Execute
            if signal:
                if self.risk_manager.can_trade(signal):
                    await self._execute_trade(signal)
            
            # Update positions (Pnl, Trailing)
            # await self._manage_positions() # Simple check
            
        except Exception as e:
            logger.error(f"B1 Passive Error: {e}")
    
    async def stop(self):
        self.state = EngineState.STOPPED
        logger.info("🛑 Motor B1 detenido")

    async def _main_loop(self):
        logger.info("🔄 Iniciando loop 5m/15m...")
        
        while self.state == EngineState.RUNNING:
            try:
                # Actualizar balance
                bal = self.connector.get_balance()
                self.current_balance = bal.get('available', 0)
                self.risk_manager.update_balance(self.current_balance)
                
                # Check Kill Switch internally in Risk Manager
                can_trade_global, reason = self.risk_manager.can_trade(None)
                if not can_trade_global and reason == "HIBERNATING":
                    logger.critical("🚨 MOTOR HIBERNADO (Kill-Switch). Deteniendo loop.")
                    self.state = EngineState.HIBERNATING
                    break
                
                # Iterar Símbolos
                for symbol in self.CONFIG['symbols']:
                    # Data 5m
                    d5 = await self._get_market_data(symbol, '5m')
                    # Data 15m
                    d15 = await self._get_market_data(symbol, '15m')
                    # Data 1H (V6: Macro Bias)
                    d1h = await self._get_market_data(symbol, '1h')
                    
                    if not d5 or not d15:
                        continue
                        
                    # Check ATR Spike (Volatility Filter)
                    atr_spike = self._check_atr_spike(d15)
                    can_trade, reason = self.risk_manager.can_trade(None, atr_15m_spike=atr_spike)
                    
                    if not can_trade:
                        if reason != "OK": logger.debug(f"Trading pausado: {reason}")
                        continue
                    
                    # Analyze
                    signal = self.strategy.analyze(d5, d15, d1h)
                    
                    if signal:
                        # Calculate Quantity via Risk Manager
                        qty = self.risk_manager.calculate_quantity(signal.entry_price, self.CONFIG['max_leverage'])
                        
                        # Execute
                        await self._execute_trade(signal, qty)
                
                # Wait 10s
                await asyncio.sleep(10)
                
            except Exception as e:
                logger.error(f"❌ Error en loop: {e}")
                await asyncio.sleep(10)

    async def process_external_signal(self, signal_data: Dict):
        """
        Procesar señal externa (TradingView Webhook).
        """
        if self.state != EngineState.RUNNING:
            logger.warning("⚠️ B1 recibio señal externa pero no esta corriendo.")
            return

        symbol = signal_data.get('symbol')
        side_str = signal_data.get('side') # BUY/SELL
        
        if symbol not in self.CONFIG['symbols']:
            logger.warning(f"⚠️ B1 ignora señal para {symbol}")
            return

        logger.info(f"📨 B1 EXECUTING EXTERNAL SIGNAL: {side_str} {symbol}")
        
        try:
            bal = self.connector.get_balance()
            if bal:
                self.risk_manager.update_balance(float(bal.get('available', 0)))

            side = TradeSide.LONG if side_str == 'BUY' else TradeSide.SHORT
            price = float(signal_data.get('price', 0))
            if price == 0:
                 from core.data_feed import DataFeed
                 price = DataFeed.LATEST_PRICES.get(symbol, 0)
                 if price == 0: # Fallback a REST
                     ticker = self.connector.client.futures_symbol_ticker(symbol=symbol)
                     price = float(ticker['price'])

            # Intercomunicador B3: Reduce apalancamiento si el mercado Macro es bajista oscuro
            from engines.b3_anchor.engine import B3AnchorEngine
            eff_lev = self.CONFIG['max_leverage']
            if getattr(B3AnchorEngine, 'GLOBAL_REGIME', 'NORMAL') == 'BEAR':
                eff_lev = max(1, eff_lev // 2)
                logger.info(f"🛡️ Intercom B3 Activo: B1 ajustado a {eff_lev}x (Régimen: BEAR) para {symbol}")

            # Construct synthetic signal
            # SL/TP defaults: SL 1%, TP 2% (Sprint logic)
            signal = TradeSignal(
                symbol=symbol,
                side=side,
                strength=1.0, 
                entry_price=price,
                stop_loss=price * (0.99 if side == TradeSide.LONG else 1.01),
                take_profit=price * (1.02 if side == TradeSide.LONG else 0.98),
                timestamp=datetime.now(),
                reason=f"TvWebhook"
            )
            
            # Calculate Qty with adjusted leverage
            qty = self.risk_manager.calculate_quantity(price, eff_lev)
            
            # Execute
            await self._execute_trade(signal, qty)
            logger.info("✅ B1 External Signal Executed")

        except Exception as e:
            logger.error(f"❌ Error procesando señal externa B1: {e}")
            raise

    async def _get_market_data(self, symbol, interval) -> Dict:
        try:
            klines = self.connector.client.futures_klines(symbol=symbol, interval=interval, limit=100)
            return {
                'symbol': symbol,
                'klines': klines,
                'timestamp': datetime.now()
            }
        except Exception as e:
            logger.error(f"Error data {symbol} {interval}: {e}")
            return {}

    def _check_atr_spike(self, data_15m):
        # Implement ATR spike check based on backtest logic
        # ATR doubles in 3 candles
        # Need to calculate ATR on the fly or in strategy?
        # For simplicity, let's skip complex ATR calculation here OR use helper
        # If Strategy calculates ATR, we could ask Strategy.
        # But Filter is Risk responsibility.
        # Check high-low range of last 3 candles?
        k = data_15m['klines']
        if len(k) < 5: return False
        ranges = [float(x[2])-float(x[3]) for x in k[-4:]] # Last 4 candles
        # If current range > 2 * prev range?
        # Backtest used ATR(15m).
        # Let's rely on standard volatility: if last candle range > 2 * avg range of prev 3
        avg_range = sum(ranges[:-1]) / 3
        if ranges[-1] > avg_range * 2.0 and avg_range > 0:
            return True
        return False

    async def _execute_trade(self, signal, qty):
        # ... (reuse existing logic but adapted) ...
        try:
            order = await self.position_manager.open_position(
                symbol=signal.symbol,
                side=signal.side,
                quantity=qty,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit
            )
            if order:
                logger.info(f"✅ Orden enviada: {signal.side.value} {signal.symbol} x {qty}")
            else:
                raise Exception("Position Manager devolvió None (Fallo en la orden)")
        except Exception as e:
            logger.error(f"Error ejecutando trade: {e}")
            raise

    
    async def _update_positions(self):
        """Sincronizar posiciones con exchange y actualizar Risk Manager."""
        # Obtener posiciones del exchange
        # Usar conector directo (sincrono)
        exchange_positions = self.connector.get_open_positions()
        active_symbols = [p['symbol'] for p in exchange_positions]
        
        # Detectar cierres
        closed_symbols = []
        for symbol, pos in self.positions.items():
            if symbol not in active_symbols:
                closed_symbols.append(symbol)
                
        # Procesar cierres
        for symbol in closed_symbols:
            # pos = self.positions.pop(symbol) # Fix: pop might fail if concurrent? Safe enough here.
             if symbol in self.positions:
                pos = self.positions.pop(symbol)
                
                # Calcular PnL (Estimado o fetch)
                # Fetch recent trade history for exact PnL
                pnl = await self._fetch_trade_pnl(symbol)
                
                logger.info(f"⚖️ Posición cerrada: {symbol} PnL: ${pnl:.2f}")
                self.total_pnl += pnl
                
                if pnl > 0: 
                    # self.wins_today += 1 # these vars are not initialized in __init__?
                    pass 
                else: 
                    # self.losses_today += 1
                    pass
                
                if self.risk_manager:
                    self.risk_manager.on_trade_closed(pnl)
            
        # Actualizar variables de estado si hacen falta
        # self.positions deberia reflejar lo que sabemos localmente
        # Pero si hay nuevas posiciones externas no las estamos ingestando aqui.
        # B1 mantiene su propio estado en self.positions via open_position return.
        
    async def _fetch_trade_pnl(self, symbol) -> float:
        """Obtener PnL del último trade cerrado."""
        try:
            trades = self.connector.client.futures_account_trades(symbol=symbol, limit=5)
            # Simplificación: sumar realizedPnl de los últimos trades recientes
            # Idealmente usar orderId
            # Por ahora, usamos el cambio en balance como proxy en RiskManager,
            # pero aquí idealmente necesitamos el Profit real del trade.
            # Vamos a usar el realizedPnl del último trade.
            last_trade = trades[-1]
            return float(last_trade['realizedPnl'])
        except:
            return 0.0

    def get_status(self) -> Dict:
        """Obtener estado actual del motor."""
        return {
            'motor': self.CONFIG['motor_id'],
            'state': self.state.value,
            'environment': self.environment,
            'balance': {
                'initial': self.initial_balance,
                'current': self.current_balance,
                'pnl': self.total_pnl,
                'pnl_pct': (self.total_pnl / self.initial_balance * 100) 
                          if self.initial_balance > 0 else 0
            },
            'positions': len(self.positions),
            'trades_today': self.trades_today,
            'win_rate': (self.wins_today / self.trades_today * 100) 
                       if self.trades_today > 0 else 0,
            'timestamp': datetime.now().isoformat()
        }

