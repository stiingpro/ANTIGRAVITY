"""
B1_SPRINT Strategy V5.1 - Rigor Híbrido 6A
==========================================
Estrategia: 5m EMA Crossover + 15m Trend Confirmation
Activos: SOLUSDT (Optimized)
"""

from typing import Optional, Dict
import logging
import math

logger = logging.getLogger('B1_Strategy')

class B1Strategy:
    """
    B1 V5.1 Strategy (Rigor Híbrido 6A).
    
    Timeframes:
    - 5m: Ejecución (EMA 9/21 Cross, VWAP, BB)
    - 15m: Confirmación (EMA 9/21 Trend Gate)
    
    Scoring:
    - Min Strength: 0.30
    - Trigger Principal: EMA Crossover (0.35)
    - Bonus: VWAP (0.15), BB Breakout (0.20), Volume (0.10)
    """
    
    def __init__(self, config: Dict):
        self.config = config
        
        # Parámetros V5.1
        self.ema_fast = config.get('ema_fast', 9)
        self.ema_slow = config.get('ema_slow', 21)
        self.bb_period = config.get('bb_period', 20)
        self.bb_std = config.get('bb_std', 2.0)
        self.vwap_lookback = config.get('vwap_lookback', 20)
        self.min_strength = 0.30  # Threshold V5.1 Relaxed
        
        logger.info("⚡ Estrategia B1 V5.1 (Rigor Híbrido 6A) inicializada")

    def analyze(self, data_5m: Dict, data_15m: Dict) -> Optional[object]:
        """
        Analizar datos de 5m y 15m para generar señal.
        """
        from engines.b1_sprint.engine import TradeSignal, TradeSide
        
        symbol = data_5m.get('symbol', 'UNKNOWN')
        
        # Extraer datos 5m
        c5 = [float(k[4]) for k in data_5m['klines']]
        h5 = [float(k[2]) for k in data_5m['klines']]
        l5 = [float(k[3]) for k in data_5m['klines']]
        v5 = [float(k[5]) for k in data_5m['klines']]
        
        # Extraer datos 15m
        c15 = [float(k[4]) for k in data_15m['klines']]
        
        if len(c5) < 50 or len(c15) < 50:
            return None

        # --- INDICADORES ---
        
        # 15m Trend Gate
        ema9_15 = self._ema(c15, self.ema_fast)
        ema21_15 = self._ema(c15, self.ema_slow)
        trend_bull = ema9_15 > ema21_15
        trend_bear = ema9_15 < ema21_15
        
        if not trend_bull and not trend_bear:
            return None # Sin tendencia clara
            
        # 5m Execution
        ema9_5 = self._ema(c5, self.ema_fast)
        ema21_5 = self._ema(c5, self.ema_slow)
        
        # Crossover logic
        cross_bull = self._ema(c5[:-1], self.ema_fast) <= self._ema(c5[:-1], self.ema_slow) and ema9_5 > ema21_5
        cross_bear = self._ema(c5[:-1], self.ema_fast) >= self._ema(c5[:-1], self.ema_slow) and ema9_5 < ema21_5
        spread_bull = ema9_5 > ema21_5
        spread_bear = ema9_5 < ema21_5
        
        # Momentum
        spread_pct = abs(ema9_5 - ema21_5) / ema21_5 * 100 if ema21_5 > 0 else 0
        momentum_strong = spread_pct > 0.15
        
        # VWAP
        vw = self._vwap(h5, l5, c5, v5, self.vwap_lookback)
        dist_vwap = (c5[-1] - vw) / vw * 100
        above_vwap = c5[-1] > vw
        below_vwap = c5[-1] < vw
        
        # Bollinger
        bb_u, bb_m, bb_l = self._bb(c5, self.bb_period, self.bb_std)
        bb_break_up = c5[-1] > bb_u
        bb_break_down = c5[-1] < bb_l
        
        # RSI
        rsi_val = self._rsi(c5, 14)
        
        # ATR (for SL/TP passing)
        
        # --- SCORING ---
        long_score = 0.0
        short_score = 0.0
        
        if trend_bull:
            if cross_bull:          long_score += 0.35
            elif spread_bull and momentum_strong:
                long_score += 0.20
            
            if above_vwap:          long_score += 0.15
            if bb_break_up:         long_score += 0.20
            if 35 <= rsi_val <= 72: long_score += 0.10
            if rsi_val > 82:        long_score -= 0.20
            
        if trend_bear:
            if cross_bear:          short_score += 0.35
            elif spread_bear and momentum_strong:
                short_score += 0.20
                
            if below_vwap:          short_score += 0.15
            if bb_break_down:       short_score += 0.20
            if 28 <= rsi_val <= 65: short_score += 0.10
            if rsi_val < 18:        short_score -= 0.20

        # --- SIGNAL GENERATION ---
        
        if long_score >= self.min_strength and long_score > short_score:
            return TradeSignal(
                symbol=symbol,
                side=TradeSide.LONG,
                strength=long_score,
                entry_price=c5[-1],
                stop_loss=0.0, # Calculated by Risk Manager
                take_profit=0.0,
                timestamp=data_5m['timestamp'],
                reason=f"V5.1 Score: {long_score:.2f} (E={cross_bull} V={above_vwap})"
            )
            
        elif short_score >= self.min_strength and short_score > long_score:
            return TradeSignal(
                symbol=symbol,
                side=TradeSide.SHORT,
                strength=min(short_score, 1.0),
                entry_price=price,
                stop_loss=round(price + sl_distance, self._price_precision(symbol)),
                take_profit=round(price - tp_distance, self._price_precision(symbol)),
                timestamp=datetime.now(),
                reason=" + ".join(short_reasons)
            )
        
        return None
    
    def _price_precision(self, symbol: str) -> int:
        """Decimales de precio según símbolo."""
        precision_map = {
            'BTCUSDT': 2, 'ETHUSDT': 2, 'BNBUSDT': 2,
            'SOLUSDT': 2, 'AVAXUSDT': 2,
            'XRPUSDT': 4, 'DOGEUSDT': 5
        }
        return precision_map.get(symbol, 2)
    
    # ========== Indicadores ==========
    
    def _ema(self, data: List[float], period: int) -> float:
        if len(data) < period:
            return sum(data) / len(data) if data else 0
        mult = 2 / (period + 1)
        ema = sum(data[:period]) / period
        for val in data[period:]:
            ema = (val * mult) + (ema * (1 - mult))
        return ema
    
    def _rsi(self, closes: List[float], period: int) -> float:
        if len(closes) < period + 1:
            return 50.0
        gains, losses = [], []
        for i in range(1, len(closes)):
            change = closes[i] - closes[i-1]
            gains.append(max(0, change))
            losses.append(max(0, -change))
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def _macd(self, closes: List[float]):
        ema12 = self._ema(closes, 12)
        ema26 = self._ema(closes, 26)
        macd_line = ema12 - ema26
        
        # Signal line from MACD series
        macd_series = []
        for i in range(26, len(closes) + 1):
            subset = closes[:i]
            e12 = self._ema(subset, 12)
            e26 = self._ema(subset, 26)
            macd_series.append(e12 - e26)
        
        macd_signal = self._ema(macd_series, 9) if len(macd_series) >= 9 else 0
        macd_hist = macd_line - macd_signal
        
        return macd_line, macd_signal, macd_hist
    
    def _macd_hist_prev(self, closes: List[float]) -> float:
        """MACD histogram of previous candle."""
        if len(closes) < 28:
            return 0
        prev = closes[:-1]
        _, _, hist = self._macd(prev)
        return hist
    
    def _atr(self, highs: List[float], lows: List[float], closes: List[float], period: int) -> float:
        if len(highs) < period + 1:
            return 0
        tr_values = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            tr_values.append(tr)
        if not tr_values:
            return 0
        return sum(tr_values[-period:]) / min(period, len(tr_values))
