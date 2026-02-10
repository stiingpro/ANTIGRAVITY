import pandas as pd
import pandas_ta as ta
from typing import Dict, Optional
from collections import namedtuple

TradeSignal = namedtuple('TradeSignal', ['symbol', 'side', 'entry_price', 'stop_loss', 'take_profit', 'reason', 'strength'])

class B3Strategy:
    """
    B3 ANCHOR STRATEGY
    Trend Momentum (Institutional)
    
    Timeframes:
    - 1D: Trend Filter (Price > EMA 200)
    - 4H: Execution (EMA 50/200 Cross + Bollinger)
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.ema_fast = config.get('ema_fast', 50)
        self.ema_slow = config.get('ema_slow', 200)
        self.bb_period = config.get('bb_period', 20)
        self.bb_std = config.get('bb_std', 2.5)
        self.atr_period = config.get('atr_period', 14)
        
    def analyze(self, data_4h: Dict, data_1d: Dict) -> Optional[TradeSignal]:
        symbol = data_4h['symbol']
        
        # 1. Preparar DataFrames
        df_4h = self._prepare_df(data_4h['klines'])
        df_1d = self._prepare_df(data_1d['klines'])
        
        if len(df_4h) < self.ema_slow or len(df_1d) < self.ema_slow:
            return None
            
        # 2. Macro Trend Filter (1D)
        # Solo operar LONG si estamos sobre la EMA 200 Diaria
        macro_ema_200 = ta.ema(df_1d['close'], length=200).iloc[-1]
        current_price = df_4h['close'].iloc[-1]
        
        if current_price < macro_ema_200:
            return None # Tendencia Macro Bajista - NO TRADE (Solo Longs en Spot/Swing)
            
        # 3. Indicadores 4H
        # EMA Cross
        ema_fast = ta.ema(df_4h['close'], length=self.ema_fast)
        ema_slow = ta.ema(df_4h['close'], length=self.ema_slow)
        
        # Bollinger Bands (para agotamiento)
        bb = ta.bbands(df_4h['close'], length=self.bb_period, std=self.bb_std)
        
        # ATR (para SL/TP)
        atr_val = ta.atr(df_4h['high'], df_4h['low'], df_4h['close'], length=self.atr_period).iloc[-1]
        
        # Valores actuales y previos
        curr_fast = ema_fast.iloc[-1]
        curr_slow = ema_slow.iloc[-1]
        prev_fast = ema_fast.iloc[-2]
        prev_slow = ema_slow.iloc[-2]
        
        # 4. Señal de Entrada (Golden Cross 4H)
        # Cruce alcista: Fast cruza arriba de Slow
        golden_cross = (prev_fast <= prev_slow) and (curr_fast > curr_slow)
        
        if golden_cross:
            # Calcular SL / TP Institucional
            # SL: 3x ATR bajo el precio (holgado)
            # TP: Abierto (Trailing) o objetivo fijo 5x ATR
            stop_loss = current_price - (atr_val * 3.0)
            take_profit = current_price + (atr_val * 6.0) # Ratio 1:2 inicial
            
            return TradeSignal(
                symbol=symbol,
                side='LONG',
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason='Golden Cross 4H + Macro Bull',
                strength=1.0
            )
            
        # 5. Señal de Salida (Exit Logic - Para gestión de posiciones abiertas, 
        # aunque el motor maneja TP/SL, la estrategia puede sugerir cierre anticipado)
        # Death Cross o Exhaustion
        death_cross = (prev_fast >= prev_slow) and (curr_fast < curr_slow)
        bb_upper = bb[f'BBU_{self.bb_period}_{self.bb_std}'].iloc[-1]
        exhaustion = current_price > bb_upper # Precio rompió banda superior con fuerza
        
        if death_cross:
            return TradeSignal(symbol, 'EXIT_LONG', current_price, 0, 0, 'Death Cross 4H', 1.0)
            
        if exhaustion:
            return TradeSignal(symbol, 'EXIT_LONG', current_price, 0, 0, 'Bollinger Exhaustion', 0.8)
            
        return None

    def _prepare_df(self, klines):
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume', 
            'close_time', 'quote_asset_volume', 'trades', 
            'taker_buy_base', 'taker_buy_quote', 'ignore'
        ])
        df['close'] = pd.to_numeric(df['close'])
        df['high'] = pd.to_numeric(df['high'])
        df['low'] = pd.to_numeric(df['low'])
        return df
