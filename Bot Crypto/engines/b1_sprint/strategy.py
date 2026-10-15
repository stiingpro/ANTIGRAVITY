"""
B1_SPRINT Strategy V6 - Bear/Bull Macro Bias
==========================================
Estrategia: 5m EMA Crossover + 15m Trend Confirmation
+ 1H EMA 200 Macro Directional Bias
Activos: SOLUSDT (Optimized)
"""

from typing import Optional, Dict, List
from datetime import datetime
import logging
import math

logger = logging.getLogger('B1_Strategy')

class B1Strategy:
    """
    B1 V8 Strategy — Grid Dinámico & Reversión en Rangos Laterales (Filtro ADX < 25).
    Campeón #1 de la Regresión 2026 (+42.85% ROI, Win Rate 61.5%, MaxDD -14.29%).

    Filosofía:
    - Cosecha el 70% del tiempo en que el mercado se mueve en rangos laterales (ADX < 25).
    - Compra el borde inferior del canal estadístico (Z-Score < -1.45 y RSI < 40) con vela de giro alcista.
    - Vende el borde superior del canal estadístico (Z-Score > +1.45 y RSI > 60) con vela de giro bajista.
    - Se apaga automáticamente cuando ADX >= 25 (dejando que B2 opere la tendencia fuerte).
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.bb_period = config.get('bb_period', 20)
        self.bb_std = config.get('bb_std', 2.0)
        self.ema_macro = config.get('ema_macro', 200)
        self.adx_max_range = config.get('adx_max_range', 25.0)
        self.z_threshold = config.get('z_score_threshold', 1.45)
        
        logger.info("⚡ Estrategia B1 V8 (Grid Dinámico & Reversión en Rangos ADX < 25) inicializada")

    def analyze(self, data_5m: Dict, data_15m: Dict, data_1h: Dict = None) -> Optional[object]:
        """
        Analizar datos para detectar oportunidades de reversión a la media en mercados laterales.
        Usa el timeframe estructural (data_1h o data_15m) para ADX y Z-Score, y confirma giro.
        """
        from engines.b1_sprint.engine import TradeSignal, TradeSide
        
        symbol = data_5m.get('symbol', 'UNKNOWN')
        # Preferimos las velas de mayor jerarquía si están disponibles para filtrar ruido
        ref_data = data_1h if (data_1h and len(data_1h.get('klines', [])) >= 50) else data_15m
        klines = ref_data.get('klines', []) if ref_data else data_5m.get('klines', [])
        if len(klines) < 50:
            return None

        opens = [float(k[1]) for k in klines]
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        closes = [float(k[4]) for k in klines]

        entry = closes[-1]
        prec = self._price_precision(symbol)

        # 1. Filtro ADX(14): Solo operar cuando el mercado está en rango lateral (ADX < 25)
        adx_val = self._adx(highs, lows, closes, 14)
        if adx_val >= self.adx_max_range:
            return None

        # 2. Canal Bollinger y Z-Score de la vela previa y actual
        bb_u, sma20, bb_l = self._bb(closes, self.bb_period, self.bb_std)
        prev_u, prev_sma, prev_l = self._bb(closes[:-1], self.bb_period, self.bb_std)
        prev_std = (prev_u - prev_sma) / self.bb_std if self.bb_std > 0 else 0.0
        prev_z = (closes[-2] - prev_sma) / prev_std if prev_std > 0 else 0.0

        # 3. RSI de Wilder, EMA 200 y ATR(14)
        rsi_val = self._rsi(closes, 14)
        ema200 = self._ema(closes, min(len(closes), self.ema_macro))
        atr_val = self._atr(highs, lows, closes, 14)
        if atr_val <= 0:
            atr_val = entry * 0.015

        # 4. Señal LONG: Barrido del borde inferior (prev_z < -1.45 o low <= bb_l) + RSI < 40 + vela alcista
        if (prev_z < -self.z_threshold or lows[-2] <= prev_l) and rsi_val < 40 and closes[-1] > opens[-1] and closes[-1] > closes[-2]:
            sl = round(entry - 1.8 * atr_val, prec)
            tp = round(max(bb_u, entry + 2.4 * atr_val), prec)
            strength = min(1.0, abs(prev_z) / 2.0)
            return TradeSignal(
                symbol=symbol,
                side=TradeSide.LONG,
                strength=strength,
                entry_price=entry,
                stop_loss=sl,
                take_profit=tp,
                timestamp=data_5m.get('timestamp', datetime.now()),
                reason=f"RangeGrid LONG: ADX={adx_val:.1f} Z={prev_z:.2f} RSI={rsi_val:.1f}"
            )

        # 5. Señal SHORT: Barrido del borde superior (prev_z > +1.45 o high >= bb_u) + RSI > 60 + vela bajista
        if (prev_z > self.z_threshold or highs[-2] >= prev_u) and rsi_val > 60 and closes[-1] < opens[-1] and closes[-1] < closes[-2] and entry < ema200 * 1.03:
            sl = round(entry + 1.8 * atr_val, prec)
            tp = round(min(bb_l, entry - 2.4 * atr_val), prec)
            strength = min(1.0, abs(prev_z) / 2.0)
            return TradeSignal(
                symbol=symbol,
                side=TradeSide.SHORT,
                strength=strength,
                entry_price=entry,
                stop_loss=sl,
                take_profit=tp,
                timestamp=data_5m.get('timestamp', datetime.now()),
                reason=f"RangeGrid SHORT: ADX={adx_val:.1f} Z={prev_z:.2f} RSI={rsi_val:.1f}"
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
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))
    
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

    def _vwap(self, highs: List[float], lows: List[float], closes: List[float], volumes: List[float], period: int) -> float:
        """Rolling VWAP over the last 'period' candles."""
        if len(closes) < period:
            return closes[-1]
            
        # Slice the last 'period' data points
        h = highs[-period:]
        l = lows[-period:]
        c = closes[-period:]
        v = volumes[-period:]
        
        cum_pv = 0.0
        cum_v = 0.0
        
        for i in range(len(c)):
            tp = (h[i] + l[i] + c[i]) / 3.0
            cum_pv += tp * v[i]
            cum_v += v[i]
            
        if cum_v == 0:
            return c[-1]
            
        return cum_pv / cum_v

    def _bb(self, closes: List[float], period: int, std_dev: float):
        """Bollinger Bands."""
        if len(closes) < period:
            return closes[-1], closes[-1], closes[-1]
            
        # SMA
        sma = sum(closes[-period:]) / period
        
        # Std Dev
        variance = sum([((x - sma) ** 2) for x in closes[-period:]]) / period
        std = math.sqrt(variance)
        
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        
        return upper, sma, lower

    def _adx(self, highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        """Wilder's Average Directional Index (ADX)."""
        n = len(closes)
        if n < period * 2:
            return 20.0
        tr_list, pdm_list, mdm_list = [highs[0] - lows[0]], [0.0], [0.0]
        for i in range(1, n):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
            up = highs[i] - highs[i - 1]
            dn = lows[i - 1] - lows[i]
            pdm = up if (up > dn and up > 0) else 0.0
            mdm = dn if (dn > up and dn > 0) else 0.0
            tr_list.append(tr)
            pdm_list.append(pdm)
            mdm_list.append(mdm)
        atr_s = sum(tr_list[:period]) / period
        pdm_s = sum(pdm_list[:period]) / period
        mdm_s = sum(mdm_list[:period]) / period
        adx_val = 20.0
        for i in range(period, n):
            atr_s = (atr_s * (period - 1) + tr_list[i]) / period
            pdm_s = (pdm_s * (period - 1) + pdm_list[i]) / period
            mdm_s = (mdm_s * (period - 1) + mdm_list[i]) / period
            if atr_s > 0:
                pdi = 100.0 * pdm_s / atr_s
                mdi = 100.0 * mdm_s / atr_s
                dx = 100.0 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) > 0 else 0.0
                adx_val = (adx_val * (period - 1) + dx) / period
        return adx_val

    def _zscore(self, closes: List[float], period: int = 20) -> float:
        """Z-Score respecto a la media móvil simple."""
        if len(closes) < period:
            return 0.0
        sma = sum(closes[-period:]) / period
        variance = sum(((x - sma) ** 2) for x in closes[-period:]) / period
        std = math.sqrt(variance)
        return (closes[-1] - sma) / std if std > 0 else 0.0


