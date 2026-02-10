"""
B2_RESILIENCE Strategy V6 — Dual-Timeframe EMA Crossover
=========================================================
Ejecución (1H): EMA 20/50 crossover + RSI momentum
Dirección (4H): EMA 200 filtro macro + ATR para SL/TP

Señales:
  LONG:  EMA20 x EMA50 ↑ (1H) + Price > EMA200 (4H) + RSI 40-70
  SHORT: EMA20 x EMA50 ↓ (1H) + Price < EMA200 (4H) + RSI 30-60
  
Salida anticipada: RSI divergence detection

Validado en backtest:
  Fase A (2023-2026): WR 59.6%, PF 1.10
  Fase B (2020-2026): WR 60.9%, PF 1.15
"""

from typing import Optional, Dict, List
from datetime import datetime
import logging
import math

logger = logging.getLogger('B2_Strategy')


class B2Strategy:
    """
    Estrategia V6 Dual-Timeframe EMA Crossover con RSI Divergence.
    
    Combina:
    1. EMA(20)/EMA(50) crossover en 1H (timing de entrada/salida)
    2. EMA(200) en 4H (filtro de dirección macro)
    3. RSI(14) en 1H (confirmación de momentum)
    4. ATR(14) en 4H (sizing dinámico de SL/TP)
    5. Volumen como confirmación adicional
    6. RSI divergence como señal de salida anticipada
    """
    
    def __init__(self, config: Dict):
        # EMA (1H)
        self.ema_fast = config.get('ema_fast', 20)
        self.ema_slow = config.get('ema_slow', 50)
        
        # EMA macro (4H)
        self.ema_macro = config.get('ema_macro', 200)
        
        # RSI
        self.rsi_period = config.get('rsi_period', 14)
        self.rsi_long_min = config.get('rsi_long_min', 40)
        self.rsi_long_max = config.get('rsi_long_max', 70)
        self.rsi_short_min = config.get('rsi_short_min', 30)
        self.rsi_short_max = config.get('rsi_short_max', 60)
        
        # ATR
        self.atr_period = config.get('atr_period', 14)
        self.sl_atr_mult = config.get('sl_atr_mult', 2.0)
        self.tp_atr_mult = config.get('tp_atr_mult', 4.0)
        
        # Señal
        self.min_strength = config.get('min_strength', 0.55)
        self.vol_threshold = config.get('vol_threshold', 0.8)
        self.vol_avg_period = 20
        
        # RSI divergence
        self.rsi_div_lookback = config.get('rsi_div_lookback', 5)
        
        # Leverage
        self.min_leverage = config.get('min_leverage', 3)
        self.max_leverage = config.get('max_leverage', 5)
    
    def analyze(self, market_data_1h: Dict, market_data_4h: Dict):
        """
        Analizar datos dual-timeframe y generar señal V6.
        
        Args:
            market_data_1h: Dict con 'symbol', 'price', 'klines' (1H)
            market_data_4h: Dict con 'symbol', 'price', 'klines' (4H)
            
        Returns:
            TradeSignal o None
        """
        from .engine import TradeSignal, TradeSide
        
        symbol = market_data_1h['symbol']
        price = market_data_1h['price']
        klines_1h = market_data_1h['klines']
        klines_4h = market_data_4h['klines']
        
        if not klines_1h or len(klines_1h) < self.ema_slow + 5:
            return None
        if not klines_4h or len(klines_4h) < self.ema_macro + 5:
            return None
        
        # ========== EXTRAER DATOS ==========
        
        # 1H data
        closes_1h = [float(k[4]) for k in klines_1h]
        highs_1h = [float(k[2]) for k in klines_1h]
        lows_1h = [float(k[3]) for k in klines_1h]
        volumes_1h = [float(k[5]) for k in klines_1h]
        
        # 4H data
        closes_4h = [float(k[4]) for k in klines_4h]
        highs_4h = [float(k[2]) for k in klines_4h]
        lows_4h = [float(k[3]) for k in klines_4h]
        
        # ========== 4H: DIRECCIÓN MACRO ==========
        
        ema200_4h = self._ema(closes_4h, self.ema_macro)
        atr_4h = self._atr(highs_4h, lows_4h, closes_4h, self.atr_period)
        price_4h = closes_4h[-1]
        
        macro_bullish = price_4h > ema200_4h
        macro_bearish = price_4h < ema200_4h
        macro_dist_pct = abs(price_4h - ema200_4h) / ema200_4h * 100 if ema200_4h > 0 else 0
        
        # ========== 1H: EJECUCIÓN ==========
        
        # EMA crossover
        ema20 = self._ema(closes_1h, self.ema_fast)
        ema50 = self._ema(closes_1h, self.ema_slow)
        prev_ema20 = self._ema(closes_1h[:-1], self.ema_fast)
        prev_ema50 = self._ema(closes_1h[:-1], self.ema_slow)
        
        bullish_cross = prev_ema20 <= prev_ema50 and ema20 > ema50
        bearish_cross = prev_ema20 >= prev_ema50 and ema20 < ema50
        ema_above = ema20 > ema50
        ema_below = ema20 < ema50
        
        # RSI
        rsi = self._rsi(closes_1h, self.rsi_period)
        
        # Volume confirmation
        vol_avg = sum(volumes_1h[-self.vol_avg_period:]) / self.vol_avg_period if len(volumes_1h) >= self.vol_avg_period else 0
        vol_confirm = volumes_1h[-1] > vol_avg * self.vol_threshold if vol_avg > 0 else False
        
        # RSI divergence
        rsi_div_bearish = self._check_rsi_divergence(closes_1h, 'bearish')
        rsi_div_bullish = self._check_rsi_divergence(closes_1h, 'bullish')
        
        # SL/TP basado en ATR(4H)
        sl_dist = atr_4h * self.sl_atr_mult if atr_4h > 0 else price * 0.02
        tp_dist = atr_4h * self.tp_atr_mult if atr_4h > 0 else price * 0.04
        
        prec = self._price_precision(symbol)
        
        # ========== SCORING LONG ==========
        long_score = 0.0
        long_reasons = []
        
        if macro_bullish:
            if bullish_cross:
                long_score += 0.35
                long_reasons.append("EMA20x50↑")
            elif ema_above:
                long_score += 0.15
                long_reasons.append("EMA20>50")
            
            if self.rsi_long_min <= rsi <= self.rsi_long_max:
                long_score += 0.20
                long_reasons.append(f"RSI={rsi:.0f}")
            
            if vol_confirm:
                long_score += 0.10
                long_reasons.append("Vol✓")
            
            if macro_dist_pct > 2.0:
                long_score += 0.15
                long_reasons.append(f">EMA200({macro_dist_pct:.1f}%)")
            elif macro_dist_pct > 0.5:
                long_score += 0.10
                long_reasons.append(">EMA200")
            
            if rsi_div_bearish:
                long_score -= 0.20
                long_reasons.append("RSIdiv↓ ⚠️")
        
        # ========== SCORING SHORT ==========
        short_score = 0.0
        short_reasons = []
        
        if macro_bearish:
            if bearish_cross:
                short_score += 0.35
                short_reasons.append("EMA20x50↓")
            elif ema_below:
                short_score += 0.15
                short_reasons.append("EMA20<50")
            
            if self.rsi_short_min <= rsi <= self.rsi_short_max:
                short_score += 0.20
                short_reasons.append(f"RSI={rsi:.0f}")
            
            if vol_confirm:
                short_score += 0.10
                short_reasons.append("Vol✓")
            
            if macro_dist_pct > 2.0:
                short_score += 0.15
                short_reasons.append(f"<EMA200({macro_dist_pct:.1f}%)")
            elif macro_dist_pct > 0.5:
                short_score += 0.10
                short_reasons.append("<EMA200")
            
            if rsi_div_bullish:
                short_score -= 0.20
                short_reasons.append("RSIdiv↑ ⚠️")
        
        # ========== GENERAR SEÑAL ==========
        
        if long_score >= self.min_strength and long_score > short_score:
            strength = min(long_score, 1.0)
            sl = round(price - sl_dist, prec)
            tp = round(price + tp_dist, prec)
            
            leverage = self._dynamic_leverage(strength)
            
            return TradeSignal(
                symbol=symbol,
                side=TradeSide.LONG,
                strength=strength,
                entry_price=round(price, prec),
                stop_loss=sl,
                take_profit=tp,
                timestamp=datetime.now(),
                reason=' + '.join(long_reasons),
                leverage=leverage
            )
        
        if short_score >= self.min_strength and short_score > long_score:
            strength = min(short_score, 1.0)
            sl = round(price + sl_dist, prec)
            tp = round(price - tp_dist, prec)
            
            leverage = self._dynamic_leverage(strength)
            
            return TradeSignal(
                symbol=symbol,
                side=TradeSide.SHORT,
                strength=strength,
                entry_price=round(price, prec),
                stop_loss=sl,
                take_profit=tp,
                timestamp=datetime.now(),
                reason=' + '.join(short_reasons),
                leverage=leverage
            )
        
        return None
    
    def check_rsi_exit(self, market_data_1h: Dict, side) -> bool:
        """
        Verificar si hay RSI divergencia para salida anticipada.
        
        Args:
            market_data_1h: Dict con klines 1H
            side: TradeSide (LONG o SHORT)
        """
        from .engine import TradeSide
        
        klines = market_data_1h.get('klines', [])
        if len(klines) < self.rsi_div_lookback + self.rsi_period + 2:
            return False
        
        closes = [float(k[4]) for k in klines]
        
        if side == TradeSide.LONG:
            return self._check_rsi_divergence(closes, 'bearish')
        else:
            return self._check_rsi_divergence(closes, 'bullish')
    
    def _check_rsi_divergence(self, closes: List[float], div_type: str) -> bool:
        """
        Detectar divergencia RSI.
        Bearish: Precio higher high + RSI lower high
        Bullish: Precio lower low + RSI higher low
        """
        n = self.rsi_div_lookback
        if len(closes) < n + self.rsi_period + 2:
            return False
        
        rsi_values = []
        for i in range(n):
            idx = len(closes) - n + i
            rsi_val = self._rsi(closes[:idx+1], self.rsi_period)
            rsi_values.append(rsi_val)
        
        recent_closes = closes[-n:]
        
        if div_type == 'bearish':
            return (recent_closes[-1] > recent_closes[0] and 
                    rsi_values[-1] < rsi_values[0] and rsi_values[-1] > 60)
        
        elif div_type == 'bullish':
            return (recent_closes[-1] < recent_closes[0] and 
                    rsi_values[-1] > rsi_values[0] and rsi_values[-1] < 40)
        
        return False
    
    def _dynamic_leverage(self, strength: float) -> int:
        """Leverage dinámico basado en fuerza de señal."""
        if strength >= 0.80:
            return self.max_leverage      # 5x
        elif strength >= 0.65:
            return min(self.max_leverage, 4)  # 4x
        else:
            return self.min_leverage      # 3x
    
    def _price_precision(self, symbol: str) -> int:
        prec_map = {
            'SOLUSDT': 2, 'AVAXUSDT': 3, 'DOTUSDT': 3,
            'ETHUSDT': 2, 'BTCUSDT': 1, 'BNBUSDT': 2,
            'LINKUSDT': 3
        }
        return prec_map.get(symbol, 2)
    
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
        return 100 - (100 / (1 + avg_gain / avg_loss))
    
    def _atr(self, highs: List[float], lows: List[float], 
             closes: List[float], period: int) -> float:
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
        return sum(tr_values[-period:]) / min(period, len(tr_values)) if tr_values else 0
