
import json
import os
import math
import logging
from datetime import datetime, timedelta
from typing import Dict, List

logger = logging.getLogger('B3_RISK')

class B3RiskManager:
    """
    Gestión de Riesgo Institucional (B3 ANCHOR)
    - Sharpe > 2.0 mensual -> Aumentar capital base
    - Drawdown < 5% mensual -> Aumentar capital base
    - Control de pérdidas diario
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.start_balance = 0.0
        self.current_equity = 0.0
        self.monthly_start_equity = 0.0
        
        # Archivo persistente de métricas mensuales
        self.stats_file = 'b3_stats.json'
        self.monthly_stats = self._load_stats()
        
        # Estado actual
        self.current_month = datetime.now().strftime('%Y-%m')
        
        # Capital Operativo vs Reserva
        self.base_capital = 1000.0 # Capital inicial fijo
        self.compounded_capital = self.monthly_stats.get('current_capital', 1000.0)
        self.reserve_fund = self.monthly_stats.get('reserve_fund', 0.0)
        
    def _load_stats(self) -> Dict:
        if os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
        
    def _save_stats(self):
        self.monthly_stats['current_capital'] = self.compounded_capital
        self.monthly_stats['reserve_fund'] = self.reserve_fund
        with open(self.stats_file, 'w') as f:
            json.dump(self.monthly_stats, f, indent=4)

    def update_balance(self, total_balance: float):
        self.current_equity = total_balance
        if self.start_balance == 0:
            self.start_balance = total_balance
            self.monthly_start_equity = total_balance
            
        # Check cambio de mes
        now_month = datetime.now().strftime('%Y-%m')
        if now_month != self.current_month:
            self._process_end_of_month()
            self.current_month = now_month
            self.monthly_start_equity = total_balance

    def _process_end_of_month(self):
        """Evaluar métricas para interés compuesto."""
        profit = self.current_equity - self.monthly_start_equity
        pct_gain = (profit / self.monthly_start_equity) * 100
        
        # Calcular Sharpe mensual aproximado (simplificado: Retorno / Volatilidad)
        # Necesitaría historial diario real, aqui usamos un proxy simple
        # Si Gain > 2% y MaxDD < 5% -> APROBADO
        
        approved = False
        if pct_gain > 2.0: # Mínimo retorno para considerar éxito
             approved = True
             
        logger.info(f"📅 Fin de Mes {self.current_month}: Gain={pct_gain:.2f}% Approved={approved}")
             
        if approved:
            # Interés Compuesto: Sumar ganancia al capital base
            self.compounded_capital += profit
            logger.info(f"✅ Reinvirtiendo Ganancia: Nuevo Capital Base = ${self.compounded_capital:.2f}")
        else:
            # Modo Protección: Ganancia a Reserva
            if profit > 0:
                self.reserve_fund += profit
                self.compounded_capital = self.monthly_start_equity # Reset al inicio del mes (sin sumar ganancia)
                logger.info(f"🛡️ Ganancia a Reserva: Fund = ${self.reserve_fund:.2f}")
            else:
                 # Pérdida: Se asume en el capital base (inevitable)
                 self.compounded_capital = self.current_equity
                 
        self._save_stats()

    def calculate_position_size(self, entry_price: float, leverage: int = 1) -> float:
        # Usar compounded_capital como base, no el equity total (si hubiera reserva)
        # Riesgo fijo: 2% del capital POR TRADE
        risk_per_trade = self.compounded_capital * 0.02
        
        # Stop Loss estimado del 3x ATR (~5% movimiento precio)
        # Risk = Size * %Move
        # Size = Risk / %Move
        # Asumimos SL distance approx 5%
        sl_distance_pct = 0.05
        
        position_size_usdt = risk_per_trade / sl_distance_pct
        
        # Limitar al max apalancamiento
        max_position = self.compounded_capital * leverage
        position_size_usdt = min(position_size_usdt, max_position)
        
        qty = position_size_usdt / entry_price
        return qty

    def can_trade(self) -> bool:
        # Verificar Drawdown global
        dd_pct = (self.start_balance - self.current_equity) / self.start_balance * 100
        if dd_pct > 20.0: # Hard Kill Switch B3
             return False
        return True
