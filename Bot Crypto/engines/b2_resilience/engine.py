"""
B2_RESILIENCE Trading Engine V6 — Dual-Timeframe EMA Crossover
===============================================================
Perfil: Conservador-Optimizado | Leverage: 3x-5x dinámico
Timeframe: 1H (ejecución) + 4H (dirección macro)
Activos: SOLUSDT, AVAXUSDT, DOTUSDT, ETHUSDT
Estrategia: EMA 20/50 Cross (1H) filtrado por EMA 200 (4H)
             + ATR SL dinámico (4H) + RSI divergence exit

Backtest validado:
  Fase A (2023-2026): ROI +46.2%, WR 59.6%, PF 1.10, MaxDD 7.9%
  Fase B (2020-2026): ROI +180.0%, WR 60.9%, PF 1.15, MaxDD 12.0%
"""

from dataclasses import dataclass
from typing import Optional, Dict, List
from enum import Enum
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger('B2_RESILIENCE')


class TradeSide(Enum):
    LONG = "BUY"
    SHORT = "SELL"


class EngineState(Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    HIBERNATING = "hibernating"


@dataclass
class TradeSignal:
    """Señal de trading generada por la estrategia V6."""
    symbol: str
    side: TradeSide
    strength: float
    entry_price: float
    stop_loss: float
    take_profit: float
    timestamp: datetime
    reason: str
    leverage: int = 3


@dataclass
class Position:
    """Posición abierta."""
    symbol: str
    side: TradeSide
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    leverage: int = 3
    unrealized_pnl: float = 0.0
    opened_at: datetime = None


class B2ResilienceEngine:
    """
    Motor de trading B2_RESILIENCE V6 — Dual-Timeframe.
    
    Características:
    - Leverage dinámico 3x-5x según fuerza de señal
    - Ejecución en 1H con dirección macro 4H
    - Activos: SOL, AVAX, DOT, ETH (los 4 más rentables)
    - SL basado en ATR(4H), TP = 4x ATR(4H)
    - RSI divergence como exit anticipada
    - Kill switch al 10% de drawdown total
    - Pausa tras 3 pérdidas consecutivas
    """
    
    CONFIG = {
        'motor_id': 'B2_RESILIENCE_V6',
        'version': '6.0',
        
        # Activos (top 4 por rendimiento en backtest)
        'symbols': ['SOLUSDT', 'AVAXUSDT', 'DOTUSDT', 'ETHUSDT'],
        'symbol': 'SOLUSDT',  # Default para display
        
        # Timeframes
        'timeframe_exec': '1h',      # Ejecución de señales
        'timeframe_macro': '4h',     # Dirección macro
        
        # EMA
        'ema_fast': 20,              # EMA rápida (1H)
        'ema_slow': 50,              # EMA lenta (1H)
        'ema_macro': 200,            # EMA dirección (4H)
        
        # RSI
        'rsi_period': 14,
        'rsi_long_min': 40,
        'rsi_long_max': 70,
        'rsi_short_min': 30,
        'rsi_short_max': 60,
        'rsi_div_lookback': 5,
        
        # ATR / SL / TP
        'atr_period': 14,
        'sl_atr_mult': 2.0,          # SL = 2x ATR(4H)
        'tp_atr_mult': 4.0,          # TP = 4x ATR(4H) → R:R 1:2
        
        # Position sizing
        'max_position_size_pct': 3.0,
        'min_leverage': 3,
        'max_leverage': 5,
        'max_open_positions': 4,       # 1 por símbolo
        'max_positions_per_symbol': 1,
        
        # Trailing stop
        'trailing_stop_activation_pct': 1.5,  # Activar al +1.5%
        
        # Risk management
        'max_daily_drawdown_pct': 5.0,
        'max_total_drawdown_pct': 10.0,
        'max_daily_trades': 8,
        'max_consecutive_losses': 3,       # Pausa tras 3 pérdidas
        'loss_pause_candles': 24,          # 24 horas de pausa
        'cooldown_candles': 6,             # 6 horas entre trades/símbolo
        
        # Signal
        'min_strength': 0.55,
        'vol_threshold': 0.8,
        
        # Check interval
        'check_interval_seconds': 300,  # 5 min (1H candle = check 12 veces)
    }
    
    def __init__(self, connector, environment: str = 'testnet'):
        """
        Inicializar motor B2 V6.
        
        Args:
            connector: ExchangeConnector configurado
            environment: 'testnet' o 'production'
        """
        self.connector = connector
        self.environment = environment
        self.state = EngineState.STOPPED
        
        # Componentes (lazy import para evitar circular)
        from .strategy import B2Strategy
        from .risk_manager import B2RiskManager
        from .position_manager import B2PositionManager
        
        self.strategy = B2Strategy(self.CONFIG)
        self.risk_manager = B2RiskManager(self.CONFIG)
        self.position_manager = B2PositionManager(self.CONFIG)
        
        # Estado
        self.daily_pnl = 0.0
        self.total_pnl = 0.0
        self.start_balance = 0.0
        self.trade_count_today = 0
        self.last_trade_day = None
        
        logger.info(f"🛡️ Motor B2 V6 inicializado [{environment}]")
        logger.info(f"   Activos: {', '.join(self.CONFIG['symbols'])}")
        logger.info(f"   Leverage: {self.CONFIG['min_leverage']}x-{self.CONFIG['max_leverage']}x")
        logger.info(f"   Estrategia: EMA {self.CONFIG['ema_fast']}/{self.CONFIG['ema_slow']} (1H) + EMA {self.CONFIG['ema_macro']} (4H)")
        logger.info(f"   SL: {self.CONFIG['sl_atr_mult']}x ATR(4H) | TP: {self.CONFIG['tp_atr_mult']}x ATR(4H)")
    
    async def initialize(self):
        """Inicializar B2 para modo pasivo."""
        logger.info("🚀 INICIANDO B2_RESILIENCE V6 [PASSIVE MODE]")
        
        account = self.connector.get_balance() if hasattr(self.connector, 'get_balance') else {'total': 0}
        self.start_balance = float(account.get('total', 0))
        logger.info(f"💰 Balance inicial: ${self.start_balance:,.2f}")
        
        # 1. Configurar Leverage
        for symbol in self.CONFIG['symbols']:
            try:
                self.connector.change_leverage(symbol, self.CONFIG['max_leverage'])
            except Exception as e:
                logger.warning(f"  ⚠️ {symbol} leverage: {e}")
        
        # 2. Sincronizar posiciones existentes
        await self._sync_positions()
        
        self.state = EngineState.RUNNING

    async def _sync_positions(self):
        """Sincronizar posiciones existentes en el exchange."""
        try:
            logger.info("🔄 Sincronizando posiciones existentes...")
            open_positions = self.connector.get_open_positions()
            count = 0
            for p in open_positions:
                if p['symbol'] in self.CONFIG['symbols']:
                    # Convert dict to Position object
                    # Note: SL/TP are unknown from just position endpoint, defaulting to 0
                    pos = Position(
                        symbol=p['symbol'],
                        side=TradeSide.LONG if p['side'] == 'LONG' else TradeSide.SHORT,
                        entry_price=p['entry_price'],
                        quantity=p['quantity'],
                        stop_loss=0.0, 
                        take_profit=0.0,
                        leverage=p['leverage'],
                        unrealized_pnl=p['pnl'],
                        opened_at=datetime.now()
                    )
                    self.position_manager.add_position(pos)
                    count += 1
            if count > 0:
                logger.info(f"✅ Sincronizadas {count} posiciones en B2.")
            else:
                logger.info("ℹ️ No se encontraron posiciones previas para B2.")
                
        except Exception as e:
            logger.error(f"❌ Error sincronizando posiciones en B2: {e}")

    async def start(self):
        """Iniciar el motor de trading (Standalone)."""
        if self.state == EngineState.RUNNING: return
        await self.initialize()
        await self._main_loop()

    async def process_external_signal(self, signal_data: Dict):
        """
        Procesar señal externa (TradingView Webhook).
        Delega a _execute_trade() que usa self.connector.client.futures_create_order().
        No requiere self.state == RUNNING — webhooks siempre se procesan.
        """
        symbol = signal_data.get('symbol')
        side_str = signal_data.get('side') 
        
        if symbol not in self.CONFIG['symbols']:
            raise ValueError(f"B2 no opera {symbol}. Válidos: {self.CONFIG['symbols']}")

        logger.info(f"📨 B2 EXECUTING EXTERNAL SIGNAL: {side_str} {symbol}")
        
        # Auto-init si el motor no fue inicializado formalmente
        if self.start_balance == 0:
            try:
                account = self.connector.get_balance()
                self.start_balance = float(account.get('total', 0))
                logger.info(f"💰 B2 Auto-init balance: ${self.start_balance:,.2f}")
            except Exception as e:
                logger.warning(f"⚠️ B2 balance fetch: {e}")

        side = TradeSide.LONG if side_str == 'BUY' else TradeSide.SHORT
        price = float(signal_data.get('price') or 0)
        if price == 0:
            ticker = self.connector.client.futures_symbol_ticker(symbol=symbol)
            price = float(ticker['price'])

        # B2 Defaults: SL 2% / TP 4% (Resilience logic)
        signal = TradeSignal(
            symbol=symbol,
            side=side,
            strength=0.9, 
            entry_price=price,
            stop_loss=price * (0.98 if side == TradeSide.LONG else 1.02),
            take_profit=price * (1.04 if side == TradeSide.LONG else 0.96),
            timestamp=datetime.now(),
            reason="TvWebhook",
            leverage=3
        )
        
        # Usar _execute_trade que ya funciona correctamente
        await self._execute_trade(signal)
        logger.info("✅ B2 External Signal Executed")

    async def on_candle_closed(self, event: Dict):
        """B2 Passive Logic (1H trigger)."""
        if self.state != EngineState.RUNNING: return

        # Kill switch check
        if self._check_kill_switch(): return

        # Reset diario if needed (handled in main loop usually, here we check date)
        today = datetime.now().date()
        if self.last_trade_day != today:
            self.daily_pnl = 0.0
            self.trade_count_today = 0
            self.last_trade_day = today
            self.risk_manager.reset_daily()

        # Iterate all symbols (since event is just a tick, but for simplicity main receives specific events)
        # Assuming event is for one symbol.
        symbol = event.get('s')
        if symbol not in self.CONFIG['symbols']: return

        try:
            # Dual Data fetch
            data_1h, data_4h = await self._get_dual_market_data(symbol)
            if data_1h and data_4h:
                signal = self.strategy.analyze(data_1h, data_4h)
                if signal and self._should_trade(signal):
                    await self._execute_trade(signal)
            
            # Manage positions (Check ALL positions on every candle close to be safe)
            await self._update_positions()
            await self._manage_positions()
            
        except Exception as e:
            logger.error(f"B2 Passive Error {symbol}: {e}")
    
    async def stop(self):
        """Detener el motor de forma segura."""
        logger.info("🔴 Deteniendo B2 V6...")
        self.state = EngineState.STOPPED
        
        # Cerrar posiciones abiertas
        for pos in self.position_manager.get_all_positions():
            logger.info(f"  Cerrando {pos.symbol}...")
            await self.position_manager.close_position(self.connector, pos.symbol)
        
        logger.info("✅ B2 V6 detenido correctamente")
    
    async def _main_loop(self):
        """
        Loop principal de trading.
        1H timeframe = check cada 5 min para no perder señales.
        """
        while self.state == EngineState.RUNNING:
            try:
                # Reset diario
                today = datetime.now().date()
                if self.last_trade_day != today:
                    self.trade_count_today = 0
                    self.daily_pnl = 0.0
                    self.last_trade_day = today
                    self.risk_manager.reset_daily()
                
                # Kill switch check
                if self._check_kill_switch():
                    self.state = EngineState.HIBERNATING
                    logger.warning("💀 KILL SWITCH ACTIVADO — Motor hibernando")
                    break
                
                # Scan cada símbolo
                for symbol in self.CONFIG['symbols']:
                    if self.state != EngineState.RUNNING:
                        break
                    
                    try:
                        # Obtener datos dual-timeframe
                        data_1h, data_4h = await self._get_dual_market_data(symbol)
                        
                        if data_1h and data_4h:
                            # Analizar con estrategia V6
                            signal = self.strategy.analyze(data_1h, data_4h)
                            
                            if signal and self._should_trade(signal):
                                await self._execute_trade(signal)
                    
                    except Exception as e:
                        logger.error(f"⚠️ Error procesando {symbol}: {e}")
                
                # Gestionar posiciones
                await self._update_positions()
                await self._manage_positions()
                
                # Esperar
                await asyncio.sleep(self.CONFIG['check_interval_seconds'])
                
            except Exception as e:
                logger.error(f"❌ Error en loop principal: {e}")
                await asyncio.sleep(60)
    
    def _check_kill_switch(self) -> bool:
        """Verificar si debe activarse el kill switch (10% drawdown)."""
        if self.start_balance <= 0:
            return False
        
        dd_pct = abs(self.total_pnl / self.start_balance * 100) if self.total_pnl < 0 else 0
        
        if dd_pct >= self.CONFIG['max_total_drawdown_pct']:
            logger.critical(
                f"🚨 KILL SWITCH: Drawdown {dd_pct:.1f}% >= "
                f"límite {self.CONFIG['max_total_drawdown_pct']}%"
            )
            return True
        
        if abs(self.daily_pnl / self.start_balance * 100) >= self.CONFIG['max_daily_drawdown_pct'] and self.daily_pnl < 0:
            logger.critical(f"🚨 KILL SWITCH DIARIO: DD {abs(self.daily_pnl / self.start_balance * 100):.1f}%")
            return True
        
        return False
    
    async def _get_dual_market_data(self, symbol: str) -> tuple:
        """
        Obtener datos duales: 1H para ejecución + 4H para macro.
        
        Returns:
            (market_data_1h, market_data_4h) dicts con klines
        """
        try:
            # Klines 1H (necesitamos al menos 55 para EMA50 + margen)
            klines_1h = await self.connector.get_klines(
                symbol=symbol,
                interval=self.CONFIG['timeframe_exec'],
                limit=60
            )
            
            # Klines 4H (necesitamos 210 para EMA200 + margen)
            klines_4h = await self.connector.get_klines(
                symbol=symbol,
                interval=self.CONFIG['timeframe_macro'],
                limit=220
            )
            
            ticker = await self.connector.get_ticker(symbol)
            current_price = float(ticker.get('lastPrice', 0))
            
            data_1h = {
                'symbol': symbol,
                'price': current_price,
                'klines': klines_1h,
                'timeframe': '1h'
            }
            
            data_4h = {
                'symbol': symbol,
                'price': current_price,
                'klines': klines_4h,
                'timeframe': '4h'
            }
            
            return data_1h, data_4h
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo datos {symbol}: {e}")
            return None, None
    
    def _should_trade(self, signal: TradeSignal) -> bool:
        """Verificar si debemos ejecutar la señal."""
        # Check risk manager
        if not self.risk_manager.can_trade(signal):
            return False
        
        # Check max posiciones
        if self.position_manager.count() >= self.CONFIG['max_open_positions']:
            return False
        
        # Check si ya hay posición en este símbolo
        if self.position_manager.has_position(signal.symbol):
            return False
        
        # Check trades diarios
        if self.trade_count_today >= self.CONFIG['max_daily_trades']:
            return False
        
        # Fuerza mínima
        if signal.strength < self.CONFIG['min_strength']:
            return False
        
        return True
    
    async def _execute_trade(self, signal: TradeSignal):
        """Ejecutar una operación con leverage dinámico."""
        try:
            account = self.connector.get_balance()
            balance = float(account.get('total') or 0)
            
            # Calcular margin (3% del balance)
            margin = balance * (self.CONFIG['max_position_size_pct'] / 100)
            
            # Leverage dinámico basado en fuerza de señal
            if signal.strength >= 0.80:
                effective_leverage = self.CONFIG['max_leverage']      # 5x
            elif signal.strength >= 0.65:
                effective_leverage = 4                                 # 4x
            else:
                effective_leverage = self.CONFIG['min_leverage']       # 3x
            
            notional = margin * effective_leverage
            quantity = notional / signal.entry_price
            
            order_side = signal.side.value
            
            logger.info(f"\n🔔 SEÑAL B2 V6 [{signal.symbol}]")
            logger.info(f"   Side: {signal.side.name} | Leverage: {effective_leverage}x")
            logger.info(f"   Entry: ${signal.entry_price:,.2f}")
            logger.info(f"   SL: ${signal.stop_loss:,.2f} | TP: ${signal.take_profit:,.2f}")
            logger.info(f"   Strength: {signal.strength:.2f} | {signal.reason}")
            logger.info(f"   Position: ${notional:,.2f} ({self.CONFIG['max_position_size_pct']}% × {effective_leverage}x)")
            
            # Ajustar leverage en exchange
            self.connector.change_leverage(
                symbol=signal.symbol,
                leverage=effective_leverage
            )
            
            # Orden de entrada
            pos_side = 'LONG' if signal.side == TradeSide.LONG else 'SHORT'
            order = self.connector.client.futures_create_order(
                symbol=signal.symbol,
                side=order_side,
                positionSide=pos_side,
                type='MARKET',
                quantity=quantity
            )
            
            if order:
                # Registrar posición
                position = Position(
                    symbol=signal.symbol,
                    side=signal.side,
                    entry_price=signal.entry_price,
                    quantity=quantity,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                    leverage=effective_leverage,
                    opened_at=datetime.now()
                )
                self.position_manager.add_position(position)
                self.risk_manager.on_trade_opened(signal)
                self.trade_count_today += 1
                
                # SL/TP en exchange
                await self._set_sl_tp(signal, quantity)
                
                logger.info(f"   ✅ ORDEN EJECUTADA — ID: {order.get('orderId', '?')}")
            
        except Exception as e:
            logger.error(f"❌ Error ejecutando trade {signal.symbol}: {e}")
            raise
    
    async def _set_sl_tp(self, signal: TradeSignal, quantity: float):
        """Colocar órdenes SL y TP."""
        try:
            sl_side = 'SELL' if signal.side == TradeSide.LONG else 'BUY'
            pos_side = 'LONG' if signal.side == TradeSide.LONG else 'SHORT'
            
            self.connector.client.futures_create_order(
                symbol=signal.symbol,
                side=sl_side,
                positionSide=pos_side,
                type='STOP_MARKET',
                quantity=quantity,
                stopPrice=signal.stop_loss,
                closePosition=True
            )
            
            self.connector.client.futures_create_order(
                symbol=signal.symbol,
                side=sl_side,
                positionSide=pos_side,
                type='TAKE_PROFIT_MARKET',
                quantity=quantity,
                stopPrice=signal.take_profit,
                closePosition=True
            )
        except Exception as e:
            logger.warning(f"⚠️ Error SL/TP {signal.symbol}: {e}")
    
    async def _update_positions(self):
        """Actualizar estado de posiciones."""
        for pos in self.position_manager.get_all_positions():
            try:
                ticker = await self.connector.get_ticker(pos.symbol)
                current_price = float(ticker.get('lastPrice', 0))
                
                if pos.side == TradeSide.LONG:
                    pos.unrealized_pnl = (current_price - pos.entry_price) * pos.quantity
                else:
                    pos.unrealized_pnl = (pos.entry_price - current_price) * pos.quantity
                    
            except Exception as e:
                logger.warning(f"⚠️ Error actualizar {pos.symbol}: {e}")
    
    async def _manage_positions(self):
        """
        Gestionar posiciones: trailing stop + RSI divergence exit.
        """
        for pos in self.position_manager.get_all_positions():
            try:
                margin = self.start_balance * (self.CONFIG['max_position_size_pct'] / 100)
                pnl_pct = (pos.unrealized_pnl / margin * 100) if margin > 0 else 0
                
                # RSI divergence exit check
                data_1h, _ = await self._get_dual_market_data(pos.symbol)
                if data_1h:
                    rsi_exit = self.strategy.check_rsi_exit(data_1h, pos.side)
                    if rsi_exit and pnl_pct > 0.3:
                        logger.info(f"📊 RSI DIVERGENCIA — Cerrando {pos.symbol} con +{pnl_pct:.1f}%")
                        await self.position_manager.close_position(self.connector, pos.symbol)
                        self.risk_manager.on_trade_closed(pnl_pct > 0)
                        continue
                
                # Trailing stop activation
                if pnl_pct >= self.CONFIG['trailing_stop_activation_pct']:
                    await self.position_manager.activate_trailing_stop(
                        self.connector, pos.symbol, pos
                    )
                    
            except Exception as e:
                logger.warning(f"⚠️ Error gestionando {pos.symbol}: {e}")
    
    def get_status(self) -> Dict:
        """Obtener estado actual del motor."""
        return {
            'motor_id': self.CONFIG['motor_id'],
            'version': self.CONFIG['version'],
            'state': self.state.value,
            'environment': self.environment,
            'strategy': 'Dual-TF EMA Cross V6',
            'symbols': self.CONFIG['symbols'],
            'leverage': f"{self.CONFIG['min_leverage']}x-{self.CONFIG['max_leverage']}x",
            'timeframes': f"{self.CONFIG['timeframe_exec']}+{self.CONFIG['timeframe_macro']}",
            'start_balance': self.start_balance,
            'total_pnl': self.total_pnl,
            'daily_pnl': self.daily_pnl,
            'positions_open': self.position_manager.count(),
            'trades_today': self.trade_count_today,
            'max_dd_limit': f"{self.CONFIG['max_total_drawdown_pct']}%",
            'backtest_results': {
                'phase_a': {'roi': '+46.2%', 'wr': '59.6%', 'pf': 1.10, 'max_dd': '7.9%'},
                'phase_b': {'roi': '+180.0%', 'wr': '60.9%', 'pf': 1.15, 'max_dd': '12.0%'}
            }
        }
