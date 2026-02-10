"""
Price Cache - Indicadores Técnicos en Tiempo Real
===================================================
Almacena velas y calcula indicadores conforme llegan datos.
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger('PriceCache')


@dataclass
class CandleStick:
    """Representación de una vela."""
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_closed: bool = False


@dataclass
class Indicators:
    """Indicadores técnicos calculados."""
    ema_9: float = 0.0
    ema_21: float = 0.0
    ema_50: float = 0.0
    rsi_14: float = 50.0
    macd_line: float = 0.0
    macd_signal: float = 0.0
    macd_histogram: float = 0.0
    atr_14: float = 0.0
    volatility: str = 'medium'
    trend: str = 'neutral'
    momentum: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


class PriceCache:
    """
    Cache de precios con cálculo de indicadores en tiempo real.
    
    Mantiene un buffer de velas y recalcula indicadores
    cada vez que se cierra una nueva vela.
    """
    
    def __init__(self, symbol: str = 'BTCUSDT', max_candles: int = 200):
        self.symbol = symbol
        self.max_candles = max_candles
        
        # Buffer de velas cerradas
        self.candles: deque = deque(maxlen=max_candles)
        
        # Vela actual (en formación)
        self.current_candle: Optional[CandleStick] = None
        
        # Último precio
        self.last_price: float = 0.0
        self.last_update: Optional[datetime] = None
        
        # Indicadores calculados
        self.indicators = Indicators()
        
        # Para cálculos incrementales
        self._ema_9_value: float = 0.0
        self._ema_21_value: float = 0.0
        self._ema_50_value: float = 0.0
        self._ema_12_value: float = 0.0
        self._ema_26_value: float = 0.0
        self._macd_signal_value: float = 0.0
        
        logger.info(f"💾 Price Cache inicializado: {symbol} ({max_candles} velas)")
    
    def update_price(self, price: float):
        """Actualizar último precio."""
        self.last_price = price
        self.last_update = datetime.now()
    
    def update_kline(self, kline_data: Dict):
        """
        Actualizar con datos de kline del WebSocket.
        
        Args:
            kline_data: Dict del WebSocket con keys:
                open, high, low, close, volume, is_closed, open_time
        """
        candle = CandleStick(
            open_time=kline_data.get('open_time', 0),
            open=kline_data['open'],
            high=kline_data['high'],
            low=kline_data['low'],
            close=kline_data['close'],
            volume=kline_data['volume'],
            is_closed=kline_data.get('is_closed', False)
        )
        
        self.last_price = candle.close
        self.last_update = datetime.now()
        
        if candle.is_closed:
            # Vela cerrada: agregar al buffer y recalcular
            self.candles.append(candle)
            self.current_candle = None
            self._recalculate_indicators()
            
            logger.debug(
                f"📊 Vela cerrada: O={candle.open:.2f} H={candle.high:.2f} "
                f"L={candle.low:.2f} C={candle.close:.2f}"
            )
        else:
            # Vela en formación
            self.current_candle = candle
    
    def load_historical(self, klines: List):
        """
        Cargar velas históricas (del REST API).
        
        Args:
            klines: Lista de klines de Binance API
        """
        self.candles.clear()
        
        for k in klines:
            candle = CandleStick(
                open_time=k[0],
                open=float(k[1]),
                high=float(k[2]),
                low=float(k[3]),
                close=float(k[4]),
                volume=float(k[5]),
                is_closed=True
            )
            self.candles.append(candle)
        
        self._recalculate_indicators()
        logger.info(f"📊 Cargadas {len(self.candles)} velas históricas")
    
    def _recalculate_indicators(self):
        """Recalcular todos los indicadores."""
        if len(self.candles) < 2:
            return
        
        closes = [c.close for c in self.candles]
        
        # EMAs
        self.indicators.ema_9 = self._calc_ema(closes, 9)
        self.indicators.ema_21 = self._calc_ema(closes, 21)
        self.indicators.ema_50 = self._calc_ema(closes, 50)
        
        # RSI
        self.indicators.rsi_14 = self._calc_rsi(closes, 14)
        
        # MACD
        ema_12 = self._calc_ema(closes, 12)
        ema_26 = self._calc_ema(closes, 26)
        self.indicators.macd_line = ema_12 - ema_26
        
        # Signal line (EMA de 9 del MACD)
        macd_values = self._calc_macd_series(closes)
        if len(macd_values) >= 9:
            self.indicators.macd_signal = self._calc_ema(macd_values, 9)
        self.indicators.macd_histogram = (
            self.indicators.macd_line - self.indicators.macd_signal
        )
        
        # ATR
        self.indicators.atr_14 = self._calc_atr(14)
        
        # Tendencia
        if self.indicators.ema_9 > self.indicators.ema_21 * 1.002:
            self.indicators.trend = 'bullish'
        elif self.indicators.ema_9 < self.indicators.ema_21 * 0.998:
            self.indicators.trend = 'bearish'
        else:
            self.indicators.trend = 'neutral'
        
        # Momentum
        if self.indicators.ema_21 > 0:
            self.indicators.momentum = (
                (self.indicators.ema_9 - self.indicators.ema_21) 
                / self.indicators.ema_21 * 100
            )
        
        # Volatilidad
        if self.last_price > 0 and self.indicators.atr_14 > 0:
            atr_pct = (self.indicators.atr_14 / self.last_price) * 100
            if atr_pct > 1.5:
                self.indicators.volatility = 'high'
            elif atr_pct < 0.5:
                self.indicators.volatility = 'low'
            else:
                self.indicators.volatility = 'medium'
        
        self.indicators.timestamp = datetime.now()
    
    def _calc_ema(self, data: List[float], period: int) -> float:
        """Calcular EMA."""
        if len(data) < period:
            return sum(data) / len(data) if data else 0
        
        multiplier = 2 / (period + 1)
        ema = sum(data[:period]) / period
        
        for price in data[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    def _calc_rsi(self, closes: List[float], period: int) -> float:
        """Calcular RSI."""
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
    
    def _calc_macd_series(self, closes: List[float]) -> List[float]:
        """Calcular serie MACD para signal line."""
        if len(closes) < 26:
            return []
        
        macd_values = []
        for i in range(26, len(closes) + 1):
            subset = closes[:i]
            ema12 = self._calc_ema(subset, 12)
            ema26 = self._calc_ema(subset, 26)
            macd_values.append(ema12 - ema26)
        
        return macd_values
    
    def _calc_atr(self, period: int) -> float:
        """Calcular ATR."""
        candles = list(self.candles)
        if len(candles) < period + 1:
            return 0
        
        tr_values = []
        for i in range(1, len(candles)):
            high = candles[i].high
            low = candles[i].low
            prev_close = candles[i-1].close
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            tr_values.append(tr)
        
        if not tr_values:
            return 0
        
        return sum(tr_values[-period:]) / min(period, len(tr_values))
    
    def get_market_data(self) -> Dict:
        """
        Obtener datos de mercado formateados para la estrategia.
        Compatible con B1Strategy.analyze()
        """
        # Convertir candles a formato klines de Binance
        klines = []
        for c in self.candles:
            klines.append([
                c.open_time,
                str(c.open),
                str(c.high),
                str(c.low),
                str(c.close),
                str(c.volume),
                c.open_time,
                "0", 0, "0", "0", "0"
            ])
        
        return {
            'symbol': self.symbol,
            'price': self.last_price,
            'klines': klines,
            'indicators': self.indicators,
            'timestamp': datetime.now()
        }
    
    def get_summary(self) -> Dict:
        """Obtener resumen del cache."""
        ind = self.indicators
        return {
            'symbol': self.symbol,
            'price': self.last_price,
            'candles': len(self.candles),
            'ema_9': round(ind.ema_9, 2),
            'ema_21': round(ind.ema_21, 2),
            'rsi': round(ind.rsi_14, 1),
            'macd': round(ind.macd_line, 2),
            'macd_signal': round(ind.macd_signal, 2),
            'atr': round(ind.atr_14, 2),
            'trend': ind.trend,
            'volatility': ind.volatility,
            'momentum': round(ind.momentum, 4),
            'last_update': self.last_update.isoformat() if self.last_update else None
        }
