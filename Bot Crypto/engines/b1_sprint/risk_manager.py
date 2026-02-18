"""
B1_SPRINT Risk Manager
======================
Gestión de riesgo para perfil agresivo.
Max position: 5% | SL: 2% | TP: 4%
"""

import logging
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger('B1_Risk')

class B1RiskManager:
    """
    B1 V5.1 Risk Manager.
    
    Features:
    - Kill Switch: 15% Max Drawdown -> Hibernation.
    - Volatility Filter: Auto-pause on ATR spikes.
    - Loss Streak Pause: 4 consecutive losses -> 24h pause.
    - Dynamic Sizing: 5% per trade.
    """
    
    def __init__(self, config: Dict, initial_balance: float):
        self.config = config
        self.initial_balance = initial_balance
        self.peak_balance = initial_balance
        self.current_balance = initial_balance
        
        # V5.1 Parameters
        self.max_dd_pct = 15.0
        self.max_consec_losses = 4
        self.loss_pause_hours = 4  # Reduced from 24h to 4h for Sprint nature
        self.atr_spike_pause_hours = 4
        self.max_pos_size_pct = 5.0
        
        # State
        self.hibernating = False
        self.paused_until: Optional[datetime] = None
        self.consecutive_losses = 0
        self.daily_pnl = 0.0
        
        logger.info(f"🛡️ Risk Manager V5.1 inicializado (Kill-Switch: -{self.max_dd_pct}%)")
        
    def update_balance(self, new_balance: float):
        """Update balance and check Kill-Switch."""
        self.current_balance = new_balance
        if new_balance > self.peak_balance:
            self.peak_balance = new_balance
            
        # Drawdown Check
        dd = (self.peak_balance - self.current_balance) / self.peak_balance * 100
        if dd >= self.max_dd_pct:
            if not self.hibernating:
                logger.critical(f"🚨 KILL SWITCH ACTIVADO! DD: {dd:.2f}% >= {self.max_dd_pct}%")
                self.hibernating = True
    
    def can_trade(self, signal, atr_15m_spike: bool = False) -> Tuple[bool, str]:
        """Check if trading is allowed."""
        if self.hibernating:
            return False, "HIBERNATING"
            
        if self.paused_until and datetime.now() < self.paused_until:
            return False, f"PAUSED until {self.paused_until}"
            
        if atr_15m_spike:
            self.pause(hours=self.atr_spike_pause_hours, reason="ATR SPIKE")
            return False, "ATR SPIKE"
            
        return True, "OK"
        
    def on_trade_closed(self, pnl: float):
        """Update state after trade close."""
        self.daily_pnl += pnl
        
        if pnl < 0:
            self.consecutive_losses += 1
            if self.consecutive_losses >= self.max_consec_losses:
                self.pause(hours=self.loss_pause_hours, reason="MAX LOSSES")
                self.consecutive_losses = 0
        else:
            self.consecutive_losses = 0
            
    def pause(self, hours: int, reason: str):
        self.paused_until = datetime.now() + timedelta(hours=hours)
        logger.warning(f"⏸️ Motor PAUSADO por {hours}h ({reason})")

    def calculate_quantity(self, entry_price: float, leverage: int = 10) -> float:
        """Calculate trade quantity (5% of equity)."""
        calc_equity = self.current_balance
        margin = calc_equity * (self.max_pos_size_pct / 100)
        notional = margin * leverage
        quantity = notional / entry_price
        
        # Redondear a 3 decimales (BTC precision)
        quantity = round(quantity, 3)
        
        # Mínimo de Binance para BTC (~$100 notional)
        min_quantity = 0.002
        if quantity < min_quantity:
            quantity = min_quantity
        
        logger.info(f"📐 Position size: {quantity} ({notional:.2f} USDT)")
        
        return quantity
    
    def calculate_leverage(self, signal, current_balance: float) -> int:
        """
        Calcular leverage óptimo basado en volatilidad y confianza.
        
        Leverage más bajo con alta volatilidad o baja confianza.
        """
        base_leverage = self.max_leverage
        
        # Reducir por baja confianza
        if signal.strength < 0.5:
            base_leverage = int(base_leverage * 0.5)
        elif signal.strength < 0.7:
            base_leverage = int(base_leverage * 0.75)
        
        # Mínimo 5x, máximo según config
        leverage = max(5, min(base_leverage, self.max_leverage))
        
        logger.debug(f"📊 Leverage calculado: {leverage}x")
        
        return leverage
    
    def _check_daily_reset(self):
        """Resetear contadores si es nuevo día."""
        today = datetime.now().date()
        if today > self.last_reset:
            self.daily_pnl = 0.0
            self.daily_trades = 0
            self.daily_losses = 0
            self.last_reset = today
            logger.info("🔄 Contadores diarios reseteados")
    
    def _is_daily_limit_reached(self, current_balance: float) -> bool:
        """Verificar si alcanzamos límite de pérdida diaria."""
        if self.initial_balance <= 0:
            return False
        
        daily_loss_pct = ((self.initial_balance - current_balance) 
                         / self.initial_balance * 100)
        
        return daily_loss_pct >= self.max_daily_loss_pct
    
    def _check_risk_reward(self, signal) -> bool:
        """Verificar ratio riesgo/recompensa mínimo."""
        risk = abs(signal.entry_price - signal.stop_loss)
        reward = abs(signal.take_profit - signal.entry_price)
        
        if risk == 0:
            return False
        
        ratio = reward / risk
        return ratio >= 1.5  # Mínimo 1.5:1
    
    def record_trade_result(self, pnl: float):
        """Registrar resultado de trade."""
        self.daily_trades += 1
        self.daily_pnl += pnl
        
        if pnl < 0:
            self.daily_losses += 1
        else:
            self.daily_losses = 0  # Reset en ganancia
    
    def get_status(self) -> Dict:
        """Obtener estado del risk manager."""
        return {
            'daily_pnl': self.daily_pnl,
            'daily_trades': self.daily_trades,
            'daily_losses': self.daily_losses,
            'max_position_pct': self.max_position_pct,
            'max_leverage': self.max_leverage,
            'current_balance': self.current_balance
        }
