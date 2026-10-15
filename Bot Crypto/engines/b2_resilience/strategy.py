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
    Estrategia V7 Dual-Timeframe EMA Crossover con RSI Divergence.
    Bear/Bull Dual Parameter Sets.
    
    Combina:
    1. EMA(20)/EMA(50) crossover en 1H (timing de entrada/salida)
    2. EMA(200) en 4H (filtro de dirección macro)
    3. RSI(14) en 1H (confirmación de momentum)
    4. ATR(14) en 4H (sizing dinámico de SL/TP)
    5. Volumen como confirmación adicional
    6. RSI divergence como señal de salida anticipada
    7. Parámetros dinámicos según régimen Bull/Bear
    """
    
    # Parámetros por régimen
    BULL_PARAMS = {
        'sl_atr_mult': 2.0,    # SL estándar
        'tp_atr_mult': 4.0,    # TP amplio (R:R 1:2)
        'rsi_long_min': 40, 'rsi_long_max': 70,
        'rsi_short_min': 30, 'rsi_short_max': 60,
        'min_strength': 0.55,
        'max_leverage': 5,
    }
    
    BEAR_PARAMS = {
        'sl_atr_mult': 1.5,    # SL más ajustado (rebotes bajistas violentos)
        'tp_atr_mult': 3.0,    # TP más corto (tomar ganancias rápido)
        'rsi_long_min': 45, 'rsi_long_max': 65,   # Más restrictivo para LONGs
        'rsi_short_min': 25, 'rsi_short_max': 55,  # Más amplio para SHORTs
        'min_strength': 0.60,  # Barra más alta
        'max_leverage': 4,     # Leverage conservador
    }
    
    def __init__(self, config: Dict):
        # EMA (1H)
        self.ema_fast = config.get('ema_fast', 20)
        self.ema_slow = config.get('ema_slow', 50)
        
        # EMA macro (4H)
        self.ema_macro = config.get('ema_macro', 200)
        
        # RSI
        self.rsi_period = config.get('rsi_period', 14)
        
        # ATR
        self.atr_period = config.get('atr_period', 14)
        
        # Señal
        self.vol_threshold = config.get('vol_threshold', 0.8)
        self.vol_avg_period = 20
        
        # RSI divergence
        self.rsi_div_lookback = config.get('rsi_div_lookback', 5)
        
        # Leverage
        self.min_leverage = config.get('min_leverage', 3)
    
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
        
        # ========== 4H: DIRECCIÓN MACRO & FUERZA RELATIVA ==========
        
        ema20_4h = self._ema(closes_4h, 20)
        ema50_4h = self._ema(closes_4h, 50)
        ema200_4h = self._ema(closes_4h, self.ema_macro)
        atr_4h = self._atr(highs_4h, lows_4h, closes_4h, self.atr_period)
        adx_4h = self._adx(highs_4h, lows_4h, closes_4h, 14)
        price_4h = closes_4h[-1]
        
        # Filtro ADX: Si ADX(4H) < 18, el activo está en rango sin tendencia (lo opera B1, no B2)
        if adx_4h < 18.0:
            return None

        # Fuerza Relativa (ROC de 7 días = 42 velas 4H, ROC de 15 días = 90 velas 4H)
        roc_7d = (price_4h / closes_4h[-42] - 1.0) * 100.0 if len(closes_4h) >= 42 else 0.0
        roc_15d = (price_4h / closes_4h[-90] - 1.0) * 100.0 if len(closes_4h) >= 90 else 0.0

        macro_bullish = price_4h > ema50_4h and (price_4h > ema200_4h or roc_15d > 6.0)
        macro_bearish = price_4h < ema50_4h and price_4h < ema200_4h
        macro_dist_pct = abs(price_4h - ema200_4h) / ema200_4h * 100 if ema200_4h > 0 else 0
        
        # ========== V8: SELECCIÓN DINÁMICA DE PARAMS ==========
        regime = self.BULL_PARAMS if macro_bullish else self.BEAR_PARAMS
        sl_atr_mult = regime['sl_atr_mult']
        tp_atr_mult = regime['tp_atr_mult']
        rsi_long_min = regime['rsi_long_min']
        rsi_long_max = regime['rsi_long_max']
        rsi_short_min = regime['rsi_short_min']
        rsi_short_max = regime['rsi_short_max']
        min_strength = regime['min_strength']
        max_leverage = min(3, regime['max_leverage'])
        
        # ========== 1H: EJECUCIÓN ==========
        
        # EMA crossover o pullback a EMA20 en líder de Fuerza Relativa
        ema20 = self._ema(closes_1h, self.ema_fast)
        ema50 = self._ema(closes_1h, self.ema_slow)
        prev_ema20 = self._ema(closes_1h[:-1], self.ema_fast)
        prev_ema50 = self._ema(closes_1h[:-1], self.ema_slow)
        
        bullish_cross = prev_ema20 <= prev_ema50 and ema20 > ema50
        bearish_cross = prev_ema20 >= prev_ema50 and ema20 < ema50
        ema_above = price > ema20 > ema50
        ema_below = price < ema20 < ema50
        
        # RSI
        rsi = self._rsi(closes_1h, self.rsi_period)
        
        # Volume confirmation
        vol_avg = sum(volumes_1h[-self.vol_avg_period:]) / self.vol_avg_period if len(volumes_1h) >= self.vol_avg_period else 0
        vol_confirm = volumes_1h[-1] > vol_avg * self.vol_threshold if vol_avg > 0 else False
        
        # RSI divergence
        rsi_div_bearish = self._check_rsi_divergence(closes_1h, 'bearish')
        rsi_div_bullish = self._check_rsi_divergence(closes_1h, 'bullish')
        
        # SL/TP basado en ATR(4H) con multiplicadores dinámicos
        sl_dist = atr_4h * sl_atr_mult if atr_4h > 0 else price * 0.025
        tp_dist = atr_4h * tp_atr_mult if atr_4h > 0 else price * 0.05
        
        prec = self._price_precision(symbol)
        
        # ========== SCORING LONG (FUERZA RELATIVA ALCISTA) ==========
        long_score = 0.0
        long_reasons = []
        
        if macro_bullish and roc_15d > 4.0:
            if bullish_cross:
                long_score += 0.35
                long_reasons.append("EMA20x50↑")
            elif ema_above and price_4h > ema20_4h:
                long_score += 0.25
                long_reasons.append("RelStrength>EMA20")
            
            if roc_15d >= 10.0:
                long_score += 0.25
                long_reasons.append(f"ROC15d=+{roc_15d:.1f}%")
            elif roc_15d >= 5.0:
                long_score += 0.15
                long_reasons.append(f"ROC15d=+{roc_15d:.1f}%")

            if rsi_long_min <= rsi <= rsi_long_max:
                long_score += 0.20
                long_reasons.append(f"RSI={rsi:.0f}")
            
            if vol_confirm:
                long_score += 0.10
                long_reasons.append("Vol✓")
            
            if rsi_div_bearish:
                long_score -= 0.25
                long_reasons.append("RSIdiv↓ ⚠️")
        
        # ========== SCORING SHORT (DEBILIDAD RELATIVA BAJISTA) ==========
        short_score = 0.0
        short_reasons = []
        
        if macro_bearish and roc_15d < -4.0:
            if bearish_cross:
                short_score += 0.35
                short_reasons.append("EMA20x50↓")
            elif ema_below and price_4h < ema20_4h:
                short_score += 0.25
                short_reasons.append("Weakness<EMA20")
            
            if roc_15d <= -10.0:
                short_score += 0.25
                short_reasons.append(f"ROC15d={roc_15d:.1f}%")
            elif roc_15d <= -5.0:
                short_score += 0.15
                short_reasons.append(f"ROC15d={roc_15d:.1f}%")

            if rsi_short_min <= rsi <= rsi_short_max:
                short_score += 0.20
                short_reasons.append(f"RSI={rsi:.0f}")
            
            if vol_confirm:
                short_score += 0.10
                short_reasons.append("Vol✓")
            
            if rsi_div_bullish:
                short_score -= 0.25
                short_reasons.append("RSIdiv↑ ⚠️")
        
        # ========== GENERAR SEÑAL ==========
        
        if long_score >= min_strength and long_score > short_score:
            strength = min(long_score, 1.0)
            sl = round(price - sl_dist, prec)
            tp = round(price + tp_dist, prec)
            
            leverage = self._dynamic_leverage(strength, max_leverage)
            
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
        
        if short_score >= min_strength and short_score > long_score:
            strength = min(short_score, 1.0)
            sl = round(price + sl_dist, prec)
            tp = round(price - tp_dist, prec)
            
            leverage = self._dynamic_leverage(strength, max_leverage)
            
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
    
    def _dynamic_leverage(self, strength: float, max_leverage: int = 5) -> int:
        """Leverage dinámico basado en fuerza de señal y régimen."""
        if strength >= 0.80:
            return max_leverage
        elif strength >= 0.65:
            return min(max_leverage, 4)
        else:
            return self.min_leverage
    
    def _price_precision(self, symbol: str) -> int:
        prec_map = {
            'SOLUSDT': 2, 'AVAXUSDT': 3, 'DOTUSDT': 3,
            'ETHUSDT': 2, 'BTCUSDT': 1, 'BNBUSDT': 2,
            'LINKUSDT': 3, 'RENDERUSDT': 3, 'UNIUSDT': 3,
            'TAOUSDT': 2, 'HYPEUSDT': 3, 'XAGUSDT': 3,
            'CLUSDT': 2
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
    
    def _rsi(self, closes: List[float], period: int = 14) -> float:
        """Wilder's RMA RSI."""
        if len(closes) < period + 1:
            return 50.0
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [max(0.0, d) for d in deltas]
        losses = [max(0.0, -d) for d in deltas]
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            return 100.0
        return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    
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

    def _adx(self, highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        """ADX direccional para confirmar fuerza de tendencia (> 18)."""
        if len(closes) < period * 2 + 1:
            return 22.0
        plus_dm, minus_dm, tr_list = [], [], []
        for i in range(1, len(closes)):
            up_move = highs[i] - highs[i - 1]
            down_move = lows[i - 1] - lows[i]
            plus_dm.append(up_move if (up_move > down_move and up_move > 0) else 0.0)
            minus_dm.append(down_move if (down_move > up_move and down_move > 0) else 0.0)
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
            tr_list.append(tr)
        dx_list = []
        for i in range(period, len(tr_list)):
            tr_sum = sum(tr_list[i - period:i])
            if tr_sum == 0:
                dx_list.append(0.0)
                continue
            p_di = 100.0 * sum(plus_dm[i - period:i]) / tr_sum
            m_di = 100.0 * sum(minus_dm[i - period:i]) / tr_sum
            denom = p_di + m_di
            dx_list.append(100.0 * abs(p_di - m_di) / denom if denom > 0 else 0.0)
        if not dx_list:
            return 22.0
        return sum(dx_list[-period:]) / min(period, len(dx_list))

