"""
B2_RESILIENCE Position Manager V6
==================================
Gestión de posiciones abiertas con trailing stop y RSI exit.
"""

import logging
from typing import Dict, Optional, List
from datetime import datetime
from .engine import TradeSide, Position

logger = logging.getLogger('B2_Positions')


class B2PositionManager:
    """
    Gestor de posiciones para B2 V6.
    
    Funciones:
    - Almacenar posiciones abiertas
    - Trailing stop dinámico
    - Cierre de posiciones
    - Estado por símbolo
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.positions: Dict[str, Position] = {}
        self.trailing_activated: Dict[str, bool] = {}
        self.trailing_stop_price: Dict[str, float] = {}
        
        self.max_positions = config.get('max_open_positions', 4)
        self.trailing_activation = config.get('trailing_stop_activation_pct', 1.5)
        
        logger.info(f"📋 Position Manager V6: max {self.max_positions} posiciones")
    
    def add_position(self, position: Position):
        """Registrar nueva posición."""
        self.positions[position.symbol] = position
        self.trailing_activated[position.symbol] = False
        logger.info(
            f"  📥 Posición abierta: {position.symbol} "
            f"{position.side.name} @ ${position.entry_price:,.2f} "
            f"(Lev: {position.leverage}x)"
        )
    
    def has_position(self, symbol: str) -> bool:
        return symbol in self.positions
    
    def count(self) -> int:
        return len(self.positions)
    
    def get_all_positions(self) -> List[Position]:
        return list(self.positions.values())
    
    async def close_position(self, connector, symbol: str) -> Optional[float]:
        """
        Cerrar posición en un símbolo.
        
        Returns:
            PnL realizado o None si falla
        """
        if symbol not in self.positions:
            return None
        
        pos = self.positions[symbol]
        
        try:
            # Cancelar órdenes abiertas
            await connector.cancel_all_orders(symbol)
            
            # Orden de cierre
            close_side = 'SELL' if pos.side == TradeSide.LONG else 'BUY'
            await connector.create_order(
                symbol=symbol,
                side=close_side,
                order_type='MARKET',
                quantity=pos.quantity,
                reduceOnly=True
            )
            
            pnl = pos.unrealized_pnl
            
            logger.info(
                f"  📤 Posición cerrada: {symbol} │ "
                f"PnL: ${pnl:+,.2f} │ "
                f"Duración: {self._duration_str(pos)}"
            )
            
            # Limpiar
            del self.positions[symbol]
            self.trailing_activated.pop(symbol, None)
            self.trailing_stop_price.pop(symbol, None)
            
            return pnl
            
        except Exception as e:
            logger.error(f"❌ Error cerrando {symbol}: {e}")
            return None
    
    async def activate_trailing_stop(self, connector, symbol: str, pos: Position):
        """Activar trailing stop para una posición en profit."""
        if self.trailing_activated.get(symbol, False):
            return
        
        try:
            # Mover SL a breakeven + 0.1%
            if pos.side == TradeSide.LONG:
                new_sl = pos.entry_price * 1.001  # BE + 0.1%
            else:
                new_sl = pos.entry_price * 0.999
            
            # Cancelar SL anterior y poner nuevo
            await connector.cancel_all_orders(symbol)
            
            sl_side = 'SELL' if pos.side == TradeSide.LONG else 'BUY'
            await connector.create_order(
                symbol=symbol,
                side=sl_side,
                order_type='STOP_MARKET',
                quantity=pos.quantity,
                stopPrice=round(new_sl, 2),
                closePosition=True
            )
            
            self.trailing_activated[symbol] = True
            self.trailing_stop_price[symbol] = new_sl
            
            logger.info(
                f"  🔒 Trailing activo: {symbol} │ "
                f"Nuevo SL: ${new_sl:,.2f} (breakeven + 0.1%)"
            )
            
        except Exception as e:
            logger.warning(f"⚠️ Error trailing {symbol}: {e}")
    
    def _duration_str(self, pos: Position) -> str:
        """Formatear duración de posición."""
        if not pos.opened_at:
            return "?"
        elapsed = datetime.now() - pos.opened_at
        hours = elapsed.total_seconds() / 3600
        if hours < 1:
            return f"{elapsed.total_seconds() / 60:.0f}min"
        elif hours < 24:
            return f"{hours:.1f}h"
        else:
            return f"{hours / 24:.1f}d"
    
    def get_status(self) -> Dict:
        """Estado actual de posiciones."""
        return {
            'total_open': len(self.positions),
            'max_positions': self.max_positions,
            'positions': {
                sym: {
                    'side': pos.side.name,
                    'entry': pos.entry_price,
                    'leverage': pos.leverage,
                    'pnl': pos.unrealized_pnl,
                    'trailing': self.trailing_activated.get(sym, False),
                    'duration': self._duration_str(pos)
                }
                for sym, pos in self.positions.items()
            }
        }
