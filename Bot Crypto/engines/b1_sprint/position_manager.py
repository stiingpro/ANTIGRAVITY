"""
B1_SPRINT Position Manager
==========================
Gestión de posiciones abiertas.
"""

import logging
from typing import Dict, Optional, List
from datetime import datetime
from .engine import TradeSide, Position

logger = logging.getLogger('B1_Position')


class B1PositionManager:
    """
    Gestor de posiciones para B1_SPRINT.
    
    Funciones:
    - Abrir posiciones con SL/TP
    - Trailing stop
    - Breakeven automático
    """
    
    def __init__(self, connector):
        self.connector = connector
        self.active_positions: Dict[str, Position] = {}
        
        logger.info("📍 Position Manager inicializado")
    
    async def open_position(
        self,
        symbol: str,
        side: TradeSide,
        quantity: float,
        stop_loss: float,
        take_profit: float
    ) -> Optional[Dict]:
        """
        Abrir nueva posición con órdenes de SL/TP.
        
        Returns:
            Dict con detalles de la orden o None si falla
        """
        try:
            logger.info(f"📈 Abriendo {side.value} {quantity} {symbol}")
            
            # 1. Orden de mercado
            order = self.connector.client.futures_create_order(
                symbol=symbol,
                side=side.value,
                type='MARKET',
                quantity=quantity
            )
            
            if order.get('status') not in ['NEW', 'FILLED']:
                logger.error(f"Orden no ejecutada: {order}")
                return None
            
            order_id = order['orderId']
            logger.info(f"✅ Orden ejecutada: {order_id}")
            
            # 2. Configurar Stop Loss
            sl_side = 'SELL' if side == TradeSide.LONG else 'BUY'
            sl_order = self.connector.client.futures_create_order(
                symbol=symbol,
                side=sl_side,
                type='STOP_MARKET',
                stopPrice=round(stop_loss, 2),
                closePosition=True
            )
            logger.info(f"🛑 Stop Loss @ ${stop_loss:.2f}")
            
            # 3. Configurar Take Profit
            tp_order = self.connector.client.futures_create_order(
                symbol=symbol,
                side=sl_side,
                type='TAKE_PROFIT_MARKET',
                stopPrice=round(take_profit, 2),
                closePosition=True
            )
            logger.info(f"🎯 Take Profit @ ${take_profit:.2f}")
            
            # Registrar posición
            position = Position(
                symbol=symbol,
                side=side,
                entry_price=float(order.get('avgPrice', 0)),
                quantity=quantity,
                stop_loss=stop_loss,
                take_profit=take_profit,
                opened_at=datetime.now()
            )
            self.active_positions[symbol] = position
            
            return {
                'order_id': order_id,
                'symbol': symbol,
                'side': side.value,
                'quantity': quantity,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'sl_order_id': sl_order.get('orderId'),
                'tp_order_id': tp_order.get('orderId')
            }
            
        except Exception as e:
            logger.error(f"❌ Error abriendo posición: {e}")
            return None
    
    async def close_position(self, symbol: str) -> bool:
        """Cerrar posición específica."""
        try:
            position = self.active_positions.get(symbol)
            if not position:
                logger.warning(f"No hay posición activa para {symbol}")
                return False
            
            # Orden de cierre
            close_side = 'SELL' if position.side == TradeSide.LONG else 'BUY'
            
            order = self.connector.client.futures_create_order(
                symbol=symbol,
                side=close_side,
                type='MARKET',
                quantity=position.quantity
            )
            
            # Cancelar órdenes pendientes (SL/TP)
            self.connector.client.futures_cancel_all_open_orders(symbol=symbol)
            
            del self.active_positions[symbol]
            logger.info(f"✅ Posición {symbol} cerrada")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error cerrando posición: {e}")
            return False
    
    async def close_all(self) -> bool:
        """Cerrar todas las posiciones (Kill Switch)."""
        logger.warning("🚨 Cerrando TODAS las posiciones...")
        
        success = True
        symbols = list(self.active_positions.keys())
        
        for symbol in symbols:
            if not await self.close_position(symbol):
                success = False
        
        return success
    
    async def update_trailing_stop(
        self,
        symbol: str,
        new_stop: float
    ) -> bool:
        """
        Actualizar trailing stop.
        Solo mueve el stop en dirección favorable.
        """
        position = self.active_positions.get(symbol)
        if not position:
            return False
        
        # Solo mover stop en dirección favorable
        if position.side == TradeSide.LONG:
            if new_stop <= position.stop_loss:
                return False
        else:
            if new_stop >= position.stop_loss:
                return False
        
        try:
            # Cancelar SL anterior
            self.connector.client.futures_cancel_all_open_orders(symbol=symbol)
            
            # Crear nuevo SL
            sl_side = 'SELL' if position.side == TradeSide.LONG else 'BUY'
            self.connector.client.futures_create_order(
                symbol=symbol,
                side=sl_side,
                type='STOP_MARKET',
                stopPrice=round(new_stop, 2),
                closePosition=True
            )
            
            position.stop_loss = new_stop
            logger.info(f"📍 Trailing stop actualizado: ${new_stop:.2f}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error actualizando trailing stop: {e}")
            return False
    
    def get_positions(self) -> List[Position]:
        """Obtener lista de posiciones activas."""
        return list(self.active_positions.values())
    
    def get_status(self) -> Dict:
        """Obtener estado del position manager."""
        return {
            'active_count': len(self.active_positions),
            'positions': [
                {
                    'symbol': p.symbol,
                    'side': p.side.value,
                    'entry': p.entry_price,
                    'quantity': p.quantity,
                    'sl': p.stop_loss,
                    'tp': p.take_profit
                }
                for p in self.active_positions.values()
            ]
        }
