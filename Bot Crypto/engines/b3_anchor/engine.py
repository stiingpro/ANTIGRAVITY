
import asyncio
import logging
from typing import Dict
from engines.b3_anchor.strategy import B3Strategy
from engines.b3_anchor.risk_manager import B3RiskManager

logger = logging.getLogger('B3_ANCHOR')

class B3AnchorEngine:
    """
    Motor B3 (ANCHOR) - V6A
    - Timeframes: 1D (Trend), 4H (Entry)
    - Assets: BTC, ETH (70%), SOL, LINK, DOT (30%)
    - Logic: Golden Cross + Compound Interest Safety
    """
    
    CONFIG = {
        'motor_id': 'B3_ANCHOR_V6A',
        'symbols': ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'LINKUSDT', 'DOTUSDT'],
        # Allocation weights could be handled by RiskManager or just equal simplified
        'timeframes': ['4h', '1d'],
        'max_leverage': 3,
        'ema_fast': 50, 'ema_slow': 200,
        'bb_period': 20, 'bb_std': 2.5
    }

    def __init__(self, connector, environment='testnet'):
        self.connector = connector
        self.env = environment
        self.running = False
        
        # Components
        self.strategy = B3Strategy(self.CONFIG)
        self.risk_manager = B3RiskManager(self.CONFIG)
        
    async def initialize(self):
        """Inicializar B3."""
        logger.info(f"⚓ MOTOR B3 ANCHOR INICIADO [PASSIVE] ({len(self.CONFIG['symbols'])} Pares)")
        self.running = True
        
        for symbol in self.CONFIG['symbols']:
            try:
                self.connector.configure_margin(symbol)
            except Exception as e:
                logger.warning(f"  ⚠️ {symbol} margin config: {e}")

        bal = await self.connector.get_balance() if asyncio.iscoroutinefunction(self.connector.get_balance) else self.connector.get_balance()
        if bal:
            self.risk_manager.update_balance(float(bal.get('total', 0) or 0))

    async def start(self):
        await self.initialize()
        await self._main_loop()

    async def process_external_signal(self, signal_data: Dict):
        """
        Procesar señal externa (TradingView Webhook).
        No requiere self.running — webhooks siempre se procesan.
        """
        symbol = signal_data.get('symbol')
        side_str = signal_data.get('side') 
        
        if symbol not in self.CONFIG['symbols']:
            raise ValueError(f"B3 no opera {symbol}. Válidos: {self.CONFIG['symbols']}")

        logger.info(f"📨 B3 EXECUTING EXTERNAL SIGNAL: {side_str} {symbol}")
        
        # Obtener precio actual si no viene en la señal
        price = float(signal_data.get('price') or 0)
        if price == 0:
            ticker = self.connector.client.futures_symbol_ticker(symbol=symbol)
            price = float(ticker['price'])

        # Asegurar que risk_manager tiene balance actualizado
        try:
            bal = self.connector.get_balance()
            if bal:
                self.risk_manager.update_balance(float(bal.get('total', 0) or 0))
        except Exception as e:
            logger.warning(f"⚠️ B3 balance fetch: {e}")

        target_side = 'LONG' if side_str == 'BUY' else 'SHORT'
        
        # SL/TP: 3% / 6% (Anchor logic)
        sl = price * (0.97 if target_side == 'LONG' else 1.03)
        tp = price * (1.06 if target_side == 'LONG' else 0.94)

        # Mock Signal Object (B3 _execute_trade espera .symbol, .side, .stop_loss, .take_profit)
        class MockSignal:
            def __init__(self, s, side, ep, sl, tp, reason):
                self.symbol = s
                self.side = side
                self.entry_price = ep
                self.stop_loss = sl
                self.take_profit = tp
                self.reason = reason

        signal = MockSignal(symbol, target_side, price, sl, tp, "TvWebhook")
        
        # Calcular cantidad (con precisión correcta para Binance)
        qty = self.risk_manager.calculate_position_size(price, self.CONFIG['max_leverage'])
        qty = self._round_qty(symbol, qty)
        if qty <= 0:
            raise ValueError(f"Cantidad calculada = 0 para {symbol} (price=${price:.2f})")
        
        # Ejecutar trade — dejar que excepciones se propaguen al webhook
        await self._execute_trade(signal, qty)
        logger.info("✅ B3 External Signal Executed")

    async def on_candle_closed(self, event: Dict):
        """B3 Passive Logic (4H trigger)."""
        if not self.running: return
        
        # Update Balance
        bal = await self.connector.get_balance() if asyncio.iscoroutinefunction(self.connector.get_balance) else self.connector.get_balance() 
        if bal:
             self.risk_manager.update_balance(float(bal.get('total', 0) or 0))
        
        if not self.risk_manager.can_trade(): return

        symbol = event.get('s')
        if symbol not in self.CONFIG['symbols']: return
        
        try:
            data_4h = await self._get_market_data(symbol, '4h')
            data_1d = await self._get_market_data(symbol, '1d')
            
            if data_4h and data_1d:
                signal = self.strategy.analyze(data_4h, data_1d)
                if signal:
                     qty = self.risk_manager.calculate_position_size(signal.entry_price, self.CONFIG['max_leverage'])
                     await self._execute_trade(signal, qty)
                     
        except Exception as e:
            logger.error(f"B3 Passive Error {symbol}: {e}")

    async def stop(self):
        self.running = False
        logger.info("⚓ MOTOR B3 DETENIDO")

    async def _main_loop(self):
        logger.info("🔄 Iniciando ciclo 4H/1D...")
        while self.running:
            try:
                # Update Balance
                bal = self.connector.get_balance()
                total_equity = bal.get('total', 0)
                self.risk_manager.update_balance(total_equity)
                
                if not self.risk_manager.can_trade():
                    logger.warning("🚨 B3 HARD KILL SWITCH ACTIVADO (-20% DD)")
                    await asyncio.sleep(60)
                    continue

                for symbol in self.CONFIG['symbols']:
                    # Get Data
                    data_4h = await self._get_market_data(symbol, '4h')
                    data_1d = await self._get_market_data(symbol, '1d')
                    
                    if not data_4h or not data_1d: continue
                    
                    # Analyze
                    signal = self.strategy.analyze(data_4h, data_1d)
                    
                    if signal:
                        logger.info(f"💪 SEÑAL {signal.side} en {symbol}: {signal.reason}")
                        qty = self.risk_manager.calculate_position_size(signal.entry_price, self.CONFIG['max_leverage'])
                        await self._execute_trade(signal, qty)
                        
                # Sleep logic: 
                # En producción, B3 es lento. Check cada 5-15 min es suficiente.
                # En Testnet/Demo aceleramos para ver actividad.
                await asyncio.sleep(60) 
                
            except Exception as e:
                logger.error(f"❌ Error B3 Loop: {e}")
                await asyncio.sleep(60)

    async def _get_market_data(self, symbol, interval):
        try:
            # Map '4h' to '4h', '1d' to '1d'
            # Connector should handle standard intervals
            limit = 300 # Need 200 EMA + buffer
            klines = self.connector.client.futures_klines(symbol=symbol, interval=interval, limit=limit)
            return {'symbol': symbol, 'klines': klines, 'timeframe': interval}
        except Exception as e:
            logger.error(f"❌ Error fetching {symbol} {interval}: {e}")
            return None

    # Precision map: decimales permitidos por Binance Futures
    QTY_PRECISION = {
        'BTCUSDT': 3, 'ETHUSDT': 3, 'SOLUSDT': 0, 'AVAXUSDT': 1,
        'DOTUSDT': 1, 'LINKUSDT': 1, 'ADAUSDT': 0, 'XRPUSDT': 1,
        'BNBUSDT': 2, 'MATICUSDT': 0, 'DOGEUSDT': 0,
    }

    @staticmethod
    def _round_qty(symbol: str, qty: float) -> float:
        """Redondear qty a la precisión válida para Binance."""
        precision = B3AnchorEngine.QTY_PRECISION.get(symbol, 3)
        import math
        factor = 10 ** precision
        return math.floor(qty * factor) / factor

    async def _execute_trade(self, signal, qty):
        """
        Ejecuta orden Hedge Mode (LONG/SHORT) con SL/TP.
        """
        symbol = signal.symbol
        side = signal.side # 'LONG'
        
        # B3 V7: Soporta LONG (Golden Cross Bull) y SHORT (Death Cross Bear)
        try:
            qty = self._round_qty(symbol, qty)
            if qty <= 0:
                raise ValueError(f"Cantidad calculada = 0 para {symbol}")
            
            logger.info(f"⚓ EJECUTANDO B3: {side} {qty} {symbol}")
            
            # 1. Market Entry
            order = await self.connector.create_order(
                symbol=symbol,
                side='BUY' if side == 'LONG' else 'SELL',
                positionSide='LONG' if side == 'LONG' else 'SHORT',
                order_type='MARKET',
                quantity=qty
            )
            logger.info(f"  ✅ Entry Filled: {order['orderId']}")
            
            # 2. Stop Loss
            await self.connector.create_order(
                symbol=symbol,
                side='SELL' if side == 'LONG' else 'BUY',
                positionSide='LONG' if side == 'LONG' else 'SHORT',
                order_type='STOP_MARKET',
                stopPrice=signal.stop_loss,
                closePosition=True
            )
            logger.info(f"  🛑 SL Set: ${signal.stop_loss}")
            
            # 3. Take Profit
            await self.connector.create_order(
                symbol=symbol,
                side='SELL' if side == 'LONG' else 'BUY',
                positionSide='LONG' if side == 'LONG' else 'SHORT',
                order_type='TAKE_PROFIT_MARKET',
                stopPrice=signal.take_profit,
                closePosition=True
            )
            logger.info(f"  🎯 TP Set: ${signal.take_profit}")
            
        except Exception as e:
            logger.error(f"❌ Error executing trade {symbol}: {e}")
            raise
