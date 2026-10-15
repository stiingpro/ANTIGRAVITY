
import asyncio
import logging
from typing import Dict
from engines.b3_anchor.strategy import B3Strategy
from engines.b3_anchor.risk_manager import B3RiskManager

logger = logging.getLogger('B3_ANCHOR')

class B3AnchorEngine:
    """
    Motor B3 (ANTI-DEBASEMENT VAULT) - V8 Champion
    - Timeframes: 1D (Macro Context), 4H (Wyckoff Deep Value Entry & Strength Exit)
    - Assets: BTCUSDT, PAXGUSDT, XAUUSDT, COPPERUSDT, SPYUSDT, ONDOUSDT
    - Logic: Wyckoff Deep Value Accumulation (RSI < 33 o Z-Score < -1.65 + Bullish Reversal)
             y Venta en Fortaleza (RSI >= 64 o Banda Superior de Bollinger)
    - Regresión 2026 (Ene-Sep): +50.05% ROI, Win Rate 63.2%, Profit Factor 1.51
    """
    
    GLOBAL_REGIME = "NORMAL" # Intercomunicador de Estado Macro
    
    CONFIG = {
        'motor_id': 'B3_ANTI_DEBASEMENT_V8',
        # Activos exclusivos de Reserva de Valor Anti-Degradación Monetaria
        'symbols': ['BTCUSDT', 'PAXGUSDT', 'XAUUSDT', 'COPPERUSDT', 'SPYUSDT', 'ONDOUSDT'],
        'timeframes': ['4h', '1d'],
        'max_leverage': 2,
        'ema_fast': 50, 'ema_slow': 200,
        'bb_period': 20, 'bb_std': 2.0,
        'rsi_buy_threshold': 33.0,
        'z_buy_threshold': -1.65,
        'rsi_sell_threshold': 64.0
    }

    def __init__(self, connector, environment='testnet'):
        self.connector = connector
        self.env = environment
        self.running = False
        self.active_positions: Dict[str, Dict] = {}
        
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
                self.connector.change_leverage(symbol, self.CONFIG['max_leverage'])
            except Exception as e:
                logger.warning(f"  ⚠️ {symbol} margin config: {e}")

        bal = await self.connector.get_balance() if asyncio.iscoroutinefunction(self.connector.get_balance) else self.connector.get_balance()
        if bal:
            self.risk_manager.update_balance(float(bal.get('total', 0) or 0))
            
        await self._sync_positions()

    async def _sync_positions(self):
        """Sincronizar posiciones abiertas de B3 en el exchange."""
        try:
            open_positions = self.connector.get_open_positions()
            for p in open_positions:
                sym = p['symbol']
                if sym in self.CONFIG['symbols']:
                    self.active_positions[sym] = {
                        'symbol': sym,
                        'side': p['side'],
                        'quantity': float(p['quantity']),
                        'entry_price': float(p['entry_price']),
                    }
            if self.active_positions:
                logger.info(f"✅ B3 sincronizó {len(self.active_positions)} posiciones activas.")
        except Exception as e:
            logger.warning(f"⚠️ B3 sync positions: {e}")

    async def start(self):
        await self.initialize()
        await self._main_loop()

    async def process_external_signal(self, signal_data: Dict):
        """
        Procesar señal externa (TradingView Webhook).
        No requiere self.running — webhooks siempre se procesan.
        Soporta Crypto, Commodities (XAUUSDT, PAXGUSDT, XAGUSDT, CLUSDT, COPPERUSDT) y Acciones/ETFs (SPYUSDT, QQQUSDT, etc.).
        """
        symbol = signal_data.get('symbol')
        side_str = signal_data.get('side') 
        
        if not symbol or not side_str:
            raise ValueError("Webhook B3 requiere 'symbol' y 'side'")

        logger.info(f"📨 B3 EXECUTING EXTERNAL SIGNAL: {side_str} {symbol}")
        
        # Obtener precio actual si no viene en la señal
        price = float(signal_data.get('price') or 0)
        if price == 0:
            ticker = await self.connector.get_ticker(symbol)
            price = float(ticker['price'])

        # Asegurar que risk_manager tiene balance actualizado
        try:
            bal = self.connector.get_balance()
            if bal:
                self.risk_manager.update_balance(float(bal.get('total', 0) or 0))
        except Exception as e:
            logger.warning(f"⚠️ B3 balance fetch: {e}")

        target_side = 'LONG' if side_str == 'BUY' else ('SHORT' if side_str == 'SELL' else side_str)
        
        custom_sl = float(signal_data.get('sl') or 0)
        custom_tp = float(signal_data.get('tp') or 0)
        # SL/TP: 3% / 6% (Anchor logic) si no vienen en el webhook
        sl = custom_sl if custom_sl > 0 else price * (0.97 if target_side == 'LONG' else 1.03)
        tp = custom_tp if custom_tp > 0 else price * (1.06 if target_side == 'LONG' else 0.94)

        class MockSignal:
            def __init__(self, s, side, ep, sl_val, tp_val, reason):
                self.symbol = s
                self.side = side
                self.entry_price = ep
                self.stop_loss = sl_val
                self.take_profit = tp_val
                self.reason = reason

        signal = MockSignal(symbol, target_side, price, sl, tp, signal_data.get('comment', 'TvWebhook'))
        
        if target_side in ('EXIT_LONG', 'EXIT_SHORT'):
            await self._execute_trade(signal, 0.0)
            return

        # Calcular cantidad (con precisión correcta para Binance)
        qty = self.risk_manager.calculate_position_size(price, self.CONFIG['max_leverage'])
        qty = self._round_qty(symbol, qty)
        if qty <= 0:
            raise ValueError(f"Cantidad calculada = 0 para {symbol} (price=${price:.2f})")
        
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
                    if signal.side in ('EXIT_LONG', 'EXIT_SHORT'):
                        await self._execute_trade(signal, 0.0)
                    else:
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
                    data_4h = await self._get_market_data(symbol, '4h')
                    data_1d = await self._get_market_data(symbol, '1d')
                    
                    if not data_4h or not data_1d: continue
                    
                    signal = self.strategy.analyze(data_4h, data_1d)
                    
                    if signal:
                        logger.info(f"💪 SEÑAL {signal.side} en {symbol}: {signal.reason}")
                        if signal.side in ('EXIT_LONG', 'EXIT_SHORT'):
                            await self._execute_trade(signal, 0.0)
                        else:
                            qty = self.risk_manager.calculate_position_size(signal.entry_price, self.CONFIG['max_leverage'])
                            await self._execute_trade(signal, qty)
                        
                await asyncio.sleep(60) 
                
            except Exception as e:
                logger.error(f"❌ Error B3 Loop: {e}")
                await asyncio.sleep(60)

    async def _get_market_data(self, symbol, interval):
        try:
            limit = 300 # Need 200 EMA + buffer
            klines = await self.connector.get_klines(symbol=symbol, interval=interval, limit=limit)
            return {'symbol': symbol, 'klines': klines, 'timeframe': interval}
        except Exception as e:
            logger.error(f"❌ Error fetching {symbol} {interval}: {e}")
            return None

    # Precision map: decimales permitidos por Binance Futures (Crypto + TradFi)
    QTY_PRECISION = {
        'BTCUSDT': 3, 'ETHUSDT': 3, 'SOLUSDT': 0, 'AVAXUSDT': 1,
        'DOTUSDT': 1, 'LINKUSDT': 1, 'ADAUSDT': 0, 'XRPUSDT': 1,
        'BNBUSDT': 2, 'MATICUSDT': 0, 'DOGEUSDT': 0, 'ONDOUSDT': 1,
        'XAUUSDT': 2, 'PAXGUSDT': 3, 'XAGUSDT': 1, 'COPPERUSDT': 1,
        'CLUSDT': 1, 'SPYUSDT': 2, 'QQQUSDT': 2, 'GDXUSDT': 1,
        'URNMUSDT': 1, 'NVDAUSDT': 1, 'TSLAUSDT': 1,
    }

    @staticmethod
    def _round_qty(symbol: str, qty: float) -> float:
        """Redondear qty a la precisión válida para Binance."""
        precision = B3AnchorEngine.QTY_PRECISION.get(symbol, 2)
        import math
        factor = 10 ** precision
        return math.floor(qty * factor) / factor

    async def close_position(self, symbol: str, target_pos_side: str = None) -> bool:
        """Cerrar posición activa en B3 de forma limpia en Hedge Mode."""
        pos = self.active_positions.get(symbol)
        if not pos:
            return False
        pos_side = target_pos_side or pos.get('side', 'LONG')
        if pos.get('side') != pos_side:
            return False
        qty = float(pos.get('quantity', 0))
        if qty <= 0:
            self.active_positions.pop(symbol, None)
            return False
        try:
            close_order_side = 'SELL' if pos_side == 'LONG' else 'BUY'
            await self.connector.cancel_all_orders(symbol=symbol, position_side=pos_side)
            await self.connector.create_order(
                symbol=symbol,
                side=close_order_side,
                positionSide=pos_side,
                order_type='MARKET',
                quantity=qty
            )
            self.active_positions.pop(symbol, None)
            logger.info(f"⚓ B3 Posición {pos_side} cerrada en {symbol} (qty={qty})")
            return True
        except Exception as e:
            logger.error(f"❌ Error cerrando posición B3 en {symbol}: {e}")
            return False

    async def _execute_trade(self, signal, qty):
        """
        Ejecuta orden Hedge Mode (LONG/SHORT) con SL/TP o cierra posición ante EXIT_LONG / EXIT_SHORT.
        """
        symbol = signal.symbol
        side = signal.side # 'LONG', 'SHORT', 'EXIT_LONG', 'EXIT_SHORT'
        
        # 1. Manejo seguro de señales de SALIDA (EXIT_LONG / EXIT_SHORT)
        if side == 'EXIT_LONG':
            if symbol in self.active_positions and self.active_positions[symbol].get('side') == 'LONG':
                logger.info(f"⚓ B3 EXIT_LONG en {symbol} ({signal.reason})")
                await self.close_position(symbol, 'LONG')
            return
        if side == 'EXIT_SHORT':
            if symbol in self.active_positions and self.active_positions[symbol].get('side') == 'SHORT':
                logger.info(f"⚓ B3 EXIT_SHORT en {symbol} ({signal.reason})")
                await self.close_position(symbol, 'SHORT')
            return

        # 2. Evitar duplicar una posición ya abierta en el mismo símbolo y dirección
        existing = self.active_positions.get(symbol)
        if existing:
            if existing.get('side') == side:
                logger.debug(f"⚓ B3 ya tiene posición {side} activa en {symbol}, ignorando duplicado.")
                return
            else:
                # Cerrar posición contraria antes de girar
                await self.close_position(symbol, existing.get('side'))

        try:
            qty = self._round_qty(symbol, qty)
            if qty <= 0:
                raise ValueError(f"Cantidad calculada = 0 para {symbol}")
            
            pos_side = 'LONG' if side == 'LONG' else 'SHORT'
            entry_order_side = 'BUY' if side == 'LONG' else 'SELL'
            exit_order_side = 'SELL' if side == 'LONG' else 'BUY'
            
            logger.info(f"⚓ EJECUTANDO B3: {pos_side} {qty} {symbol}")
            
            # 1. Market Entry
            order = await self.connector.create_order(
                symbol=symbol,
                side=entry_order_side,
                positionSide=pos_side,
                order_type='MARKET',
                quantity=qty
            )
            logger.info(f"  ✅ Entry Filled: {order.get('orderId')}")
            
            self.active_positions[symbol] = {
                'symbol': symbol,
                'side': pos_side,
                'quantity': qty,
                'entry_price': float(order.get('avgPrice', 0) or signal.entry_price),
                'stop_loss': signal.stop_loss,
                'take_profit': signal.take_profit,
            }
            
            # 2. Stop Loss (con quantity explícito, closePosition=False)
            if signal.stop_loss and signal.stop_loss > 0:
                await self.connector.create_order(
                    symbol=symbol,
                    side=exit_order_side,
                    positionSide=pos_side,
                    order_type='STOP_MARKET',
                    stopPrice=round(signal.stop_loss, 2),
                    quantity=qty,
                    closePosition=False
                )
                logger.info(f"  🛑 SL Set: ${signal.stop_loss:.2f}")
            
            # 3. Take Profit (con quantity explícito, closePosition=False)
            if signal.take_profit and signal.take_profit > 0:
                await self.connector.create_order(
                    symbol=symbol,
                    side=exit_order_side,
                    positionSide=pos_side,
                    order_type='TAKE_PROFIT_MARKET',
                    stopPrice=round(signal.take_profit, 2),
                    quantity=qty,
                    closePosition=False
                )
                logger.info(f"  🎯 TP Set: ${signal.take_profit:.2f}")
            
        except Exception as e:
            logger.error(f"❌ Error executing trade {symbol}: {e}")
            raise
