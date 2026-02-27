import pandas as pd

from typing import Dict, Optional
from collections import namedtuple

TradeSignal = namedtuple('TradeSignal', ['symbol', 'side', 'entry_price', 'stop_loss', 'take_profit', 'reason', 'strength'])

class B3Strategy:
    """
    B3 ANCHOR STRATEGY V7 — Bear/Bull Dual Strategy
    
    Timeframes:
    - 1D: Trend Filter (Price vs EMA 200) → determina régimen BULL/BEAR
    - 4H: Execution (EMA 50/200 Cross + Bollinger)
    
    BULL: Golden Cross (EMA50 x EMA200 4H) → LONG
    BEAR: Death Cross (EMA50 x EMA200 4H) → SHORT
    """
    
    # Parámetros por régimen
    BULL_PARAMS = {
        'sl_atr_mult': 3.0,   # SL holgado para swing largo
        'tp_atr_mult': 6.0,   # TP amplio para capturar tendencia
    }
    
    BEAR_PARAMS = {
        'sl_atr_mult': 2.5,   # SL más ajustado (rebotes bajistas son violentos)
        'tp_atr_mult': 5.0,   # TP agresivo (caídas son rápidas)
    }
    
    def __init__(self, config: Dict):
        self.config = config
        self.ema_fast = config.get('ema_fast', 50)
        self.ema_slow = config.get('ema_slow', 200)
        self.bb_period = config.get('bb_period', 20)
        self.bb_std = config.get('bb_std', 2.5)
        self.atr_period = config.get('atr_period', 14)
        
    def analyze(self, data_4h: Dict, data_1d: Dict) -> Optional[TradeSignal]:
        import core.indicators as ind
        
        symbol = data_4h['symbol']
        
        # 1. Preparar DataFrames
        df_4h = self._prepare_df(data_4h['klines'])
        df_1d = self._prepare_df(data_1d['klines'])
        
        if len(df_4h) < self.ema_slow or len(df_1d) < self.ema_slow:
            return None
            
        # 2. Macro Trend Filter (1D) — Determina régimen
        macro_ema_200 = ind.calculate_ema(df_1d['close'], self.ema_slow).iloc[-1]
        current_price = df_4h['close'].iloc[-1]
        
        is_bull = current_price > macro_ema_200
        is_bear = current_price < macro_ema_200
        
        # Seleccionar parámetros según régimen
        params = self.BULL_PARAMS if is_bull else self.BEAR_PARAMS
            
        # 3. Indicadores 4H
        ema_fast_series = ind.calculate_ema(df_4h['close'], self.ema_fast)
        ema_slow_series = ind.calculate_ema(df_4h['close'], self.ema_slow)
        
        # Bollinger Bands
        bb_upper, _, bb_lower = ind.calculate_bbands(df_4h['close'], self.bb_period, self.bb_std)
        
        # ATR (para SL/TP)
        atr_series = ind.calculate_atr(df_4h['high'], df_4h['low'], df_4h['close'], self.atr_period)
        atr_val = atr_series.iloc[-1]
        
        # Valores actuales y previos
        curr_fast = ema_fast_series.iloc[-1]
        curr_slow = ema_slow_series.iloc[-1]
        prev_fast = ema_fast_series.iloc[-2]
        prev_slow = ema_slow_series.iloc[-2]
        
        # Detección de cruces
        golden_cross = (prev_fast <= prev_slow) and (curr_fast > curr_slow)
        death_cross = (prev_fast >= prev_slow) and (curr_fast < curr_slow)
        
        # ═══ BULL STRATEGY: Golden Cross → LONG ═══
        if is_bull and golden_cross:
            stop_loss = current_price - (atr_val * params['sl_atr_mult'])
            take_profit = current_price + (atr_val * params['tp_atr_mult'])
            
            return TradeSignal(
                symbol=symbol,
                side='LONG',
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason='Golden Cross 4H + Macro Bull',
                strength=1.0
            )
        
        # ═══ BEAR STRATEGY: Death Cross → SHORT (NUEVO V7) ═══
        if is_bear and death_cross:
            stop_loss = current_price + (atr_val * params['sl_atr_mult'])
            take_profit = current_price - (atr_val * params['tp_atr_mult'])
            
            return TradeSignal(
                symbol=symbol,
                side='SHORT',
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason='Death Cross 4H + Macro Bear',
                strength=1.0
            )
        
        # ═══ EXIT SIGNALS ═══
        bb_u = bb_upper.iloc[-1]
        bb_l = bb_lower.iloc[-1]
        
        # Exit LONG: Death Cross en bull o BB upper exhaustion
        if is_bull and death_cross:
            return TradeSignal(symbol, 'EXIT_LONG', current_price, 0, 0, 'Death Cross 4H (Bull Exit)', 1.0)
        
        if is_bull and current_price > bb_u:
            return TradeSignal(symbol, 'EXIT_LONG', current_price, 0, 0, 'Bollinger Upper Exhaustion', 0.8)
        
        # Exit SHORT: Golden Cross en bear o BB lower exhaustion
        if is_bear and golden_cross:
            return TradeSignal(symbol, 'EXIT_SHORT', current_price, 0, 0, 'Golden Cross 4H (Bear Exit)', 1.0)
        
        if is_bear and current_price < bb_l:
            return TradeSignal(symbol, 'EXIT_SHORT', current_price, 0, 0, 'Bollinger Lower Exhaustion', 0.8)
            
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
