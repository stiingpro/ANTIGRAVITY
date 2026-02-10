"""
B2_RESILIENCE Risk Manager V6
==============================
Gestión de riesgo para perfil conservador-optimizado.
Leverage dinámico: 3x-5x | Max pos: 3% | Max DD: 10%
Pausa tras 3 pérdidas consecutivas (24h cooldown)
"""

import logging
from typing import Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger('B2_Risk')


class B2RiskManager:
    """
    Risk Manager V6 con leverage dinámico y control adaptativo.
    
    Reglas:
    1. Max position size: 3% del balance
    2. Leverage dinámico: 3x (débil) → 4x (media) → 5x (fuerte)
    3. Max 4 posiciones abiertas simultáneas
    4. Max 8 trades/día
    5. Pausa 24h tras 3 pérdidas consecutivas
    6. Max daily drawdown: 5%
    7. Kill switch total: 10% drawdown
    8. Cooldown 6h entre trades del mismo símbolo
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.max_position_pct = config.get('max_position_size_pct', 3.0)
        self.max_daily_dd = config.get('max_daily_drawdown_pct', 5.0)
        self.max_total_dd = config.get('max_total_drawdown_pct', 10.0)
        self.max_daily_trades = config.get('max_daily_trades', 8)
        self.max_consecutive_losses = config.get('max_consecutive_losses', 3)
        self.loss_pause_hours = config.get('loss_pause_candles', 24)
        self.cooldown_hours = config.get('cooldown_candles', 6)
        
        # Estado
        self.consecutive_losses = 0
        self.daily_trades = 0
        self.daily_pnl = 0.0
        self.total_pnl = 0.0
        self.last_trade_time: Dict[str, datetime] = {}
        self.paused_until: Optional[datetime] = None
        self.start_balance = 0.0
        
        logger.info("🛡️ Risk Manager V6 inicializado")
        logger.info(f"   Max posición: {self.max_position_pct}%")
        logger.info(f"   Max DD diario: {self.max_daily_dd}%")
        logger.info(f"   Max DD total: {self.max_total_dd}%")
        logger.info(f"   Pausa tras: {self.max_consecutive_losses} pérdidas → {self.loss_pause_hours}h")
    
    def can_trade(self, signal) -> bool:
        """
        Verificar si se permite abrir un trade.
        
        Returns:
            True si el trade cumple todas las reglas de riesgo
        """
        now = datetime.now()
        
        # 1. Pausa activa por pérdidas consecutivas
        if self.paused_until and now < self.paused_until:
            remaining = (self.paused_until - now).total_seconds() / 3600
            logger.info(f"  ⏸️ Pausa activa: {remaining:.1f}h restantes")
            return False
        elif self.paused_until and now >= self.paused_until:
            self.paused_until = None
            self.consecutive_losses = 0
            logger.info("  ▶️ Pausa terminada — Trading reanudado")
        
        # 2. Max trades diarios
        if self.daily_trades >= self.max_daily_trades:
            logger.debug(f"  🚫 Max trades diarios alcanzado: {self.daily_trades}/{self.max_daily_trades}")
            return False
        
        # 3. Daily drawdown
        if self.start_balance > 0:
            dd = abs(self.daily_pnl / self.start_balance * 100) if self.daily_pnl < 0 else 0
            if dd >= self.max_daily_dd:
                logger.warning(f"  🚫 Max DD diario: {dd:.1f}% >= {self.max_daily_dd}%")
                return False
        
        # 4. Cooldown por símbolo
        symbol = signal.symbol
        if symbol in self.last_trade_time:
            elapsed = (now - self.last_trade_time[symbol]).total_seconds() / 3600
            if elapsed < self.cooldown_hours:
                logger.debug(f"  ⏳ Cooldown {symbol}: {elapsed:.1f}h / {self.cooldown_hours}h")
                return False
        
        return True
    
    def on_trade_opened(self, signal):
        """Registrar apertura de trade."""
        self.daily_trades += 1
        self.last_trade_time[signal.symbol] = datetime.now()
        logger.info(
            f"  📝 Trade #{self.daily_trades}/{self.max_daily_trades}: "
            f"{signal.symbol} {signal.side.name} "
            f"(Lev: {getattr(signal, 'leverage', '?')}x, Str: {signal.strength:.2f})"
        )
    
    def on_trade_closed(self, is_win: bool, pnl_usd: float = 0.0):
        """
        Registrar cierre de trade y actualizar estado.
        
        Args:
            is_win: True si el trade fue ganador
            pnl_usd: PnL en USD
        """
        self.daily_pnl += pnl_usd
        self.total_pnl += pnl_usd
        
        if is_win:
            self.consecutive_losses = 0
            logger.info(f"  ✅ Trade ganador | Racha pérdidas: RESET")
        else:
            self.consecutive_losses += 1
            logger.info(
                f"  ❌ Trade perdedor | Racha: {self.consecutive_losses}/"
                f"{self.max_consecutive_losses}"
            )
            
            # Activar pausa si alcanza máximo
            if self.consecutive_losses >= self.max_consecutive_losses:
                self.paused_until = datetime.now() + timedelta(hours=self.loss_pause_hours)
                logger.warning(
                    f"  ⏸️ PAUSA ACTIVADA: {self.consecutive_losses} "
                    f"pérdidas consecutivas → {self.loss_pause_hours}h pausa "
                    f"hasta {self.paused_until.strftime('%H:%M')}"
                )
    
    def reset_daily(self):
        """Reset de contadores diarios (llamar al inicio del día)."""
        prev_pnl = self.daily_pnl
        self.daily_trades = 0
        self.daily_pnl = 0.0
        logger.info(f"  🔄 Reset diario | PnL ayer: ${prev_pnl:+,.2f}")
    
    def get_status(self) -> Dict:
        """Obtener estado actual del risk manager."""
        now = datetime.now()
        paused = self.paused_until is not None and now < self.paused_until
        pause_remaining = 0
        if paused:
            pause_remaining = (self.paused_until - now).total_seconds() / 3600
        
        return {
            'consecutive_losses': self.consecutive_losses,
            'daily_trades': self.daily_trades,
            'max_daily_trades': self.max_daily_trades,
            'daily_pnl': self.daily_pnl,
            'total_pnl': self.total_pnl,
            'paused': paused,
            'pause_remaining_hours': round(pause_remaining, 1),
            'cooldown_hours': self.cooldown_hours,
            'max_position_pct': self.max_position_pct,
            'max_daily_dd': self.max_daily_dd,
            'max_total_dd': self.max_total_dd,
        }
