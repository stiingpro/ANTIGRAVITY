
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
        
        bal = await self.connector.get_balance() if asyncio.iscoroutinefunction(self.connector.get_balance) else self.connector.get_balance()
        if bal:
            self.risk_manager.update_balance(float(bal.get('total', 0) or 0))

    async def start(self):
        await self.initialize()
        await self._main_loop()

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

    async def _execute_trade(self, signal, qty):
        """
        Ejecuta orden Hedge Mode (LONG/SHORT) con SL/TP.
        """
        symbol = signal.symbol
        side = signal.side # 'LONG'
        
        # B3 solo opera LONG en principio por diseño (Golden Cross)
        # Pero si la estrategia diera SHORT (Death Cross inversion?), lo soportamos.
        # Por ahora asumimos LONG.
        
        try:
            logger.info(f"⚓ EJECUTANDO B3: {side} {qty} {symbol}")
            
            # 1. Market Entry
            order = self.connector.client.futures_create_order(
                symbol=symbol,
                side='BUY' if side == 'LONG' else 'SELL',
                positionSide='LONG' if side == 'LONG' else 'SHORT',
                type='MARKET',
                quantity=qty
            )
            logger.info(f"  ✅ Entry Filled: {order['orderId']}")
            
            # 2. Stop Loss
            self.connector.client.futures_create_order(
                symbol=symbol,
                side='SELL' if side == 'LONG' else 'BUY',
                positionSide='LONG' if side == 'LONG' else 'SHORT',
                type='STOP_MARKET',
                stopPrice=round(signal.stop_loss, 2), # TODO: Precision dinamica
                closePosition=True
            )
            logger.info(f"  🛑 SL Set: ${signal.stop_loss}")
            
            # 3. Take Profit
            self.connector.client.futures_create_order(
                symbol=symbol,
                side='SELL' if side == 'LONG' else 'BUY',
                positionSide='LONG' if side == 'LONG' else 'SHORT',
                type='TAKE_PROFIT_MARKET',
                stopPrice=round(signal.take_profit, 2),
                closePosition=True
            )
            logger.info(f"  🎯 TP Set: ${signal.take_profit}")
            
        except Exception as e:
            logger.error(f"❌ Error executing trade {symbol}: {e}")
