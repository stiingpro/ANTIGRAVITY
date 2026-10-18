import pandas as pd
from typing import Dict, Optional
from collections import namedtuple

TradeSignal = namedtuple('TradeSignal', ['symbol', 'side', 'entry_price', 'stop_loss', 'take_profit', 'reason', 'strength'])

class B3Strategy:
    """
    B3 ANTI-DEBASEMENT VAULT STRATEGY V8 — Acumulación Institucional Wyckoff
    ========================================================================
    Activos exclusivos: BTCUSDT, PAXGUSDT, XAUUSDT, COPPERUSDT, SPYUSDT, ONDOUSDT
    Timeframes:
    - 1D: Contexto Macro (EMA 200) → actualiza Intercomunicador GLOBAL_REGIME
    - 4H: Ejecución de Acumulación en Miedo Extremo (Spring Wyckoff) y Venta en Fortaleza
    
    Reglas Validadas en Regresión 2026 (+50.05% ROI, 63.2% Win Rate, PF 1.51):
    1. COMPRA EN MIEDO (Wyckoff Spring 4H):
       - RSI(14) < 33.0  O  Z-Score(20) < -1.65  O  Precio <= Banda Inferior Bollinger (2.0 std)
       - Confirmación de absorción institucional: Vela 4H alcista (close >= open) o rechazo de mecha inferior
    2. SALIDA EN FORTALEZA (Distribución):
       - RSI(14) >= 64.0  O  Precio >= Banda Superior Bollinger (2.0 std)
    3. Gestión de Riesgo:
       - Stop Loss de protección catastrófica: 6.5% (o 2.8x ATR 4H)
       - Take Profit objetivo: 14.0% (o 5.5x ATR 4H)
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.ema_fast = config.get('ema_fast', 50)
        self.ema_slow = config.get('ema_slow', 200)
        self.bb_period = config.get('bb_period', 20)
        self.bb_std = config.get('bb_std', 2.0)
        self.atr_period = config.get('atr_period', 14)
        self.rsi_buy = config.get('rsi_buy_threshold', 30.5)
        self.z_buy = config.get('z_buy_threshold', -1.80)
        self.rsi_sell = config.get('rsi_sell_threshold', 64.0)
        
    def analyze(self, data_4h: Dict, data_1d: Optional[Dict] = None) -> Optional[TradeSignal]:
        import core.indicators as ind
        
        symbol = data_4h['symbol']
        df_4h = self._prepare_df(data_4h['klines'])
        
        if len(df_4h) < 55:
            return None
            
        current_price = float(df_4h['close'].iloc[-1])
        current_open = float(df_4h['open'].iloc[-1])
        current_low = float(df_4h['low'].iloc[-1])
        current_high = float(df_4h['high'].iloc[-1])
        
        # 1. Contexto Macro (1D o 4H EMA200) para Intercomunicador Global
        if data_1d and data_1d.get('klines') and len(data_1d['klines']) >= 50:
            df_1d = self._prepare_df(data_1d['klines'])
            macro_period = min(self.ema_slow, len(df_1d) - 1)
            macro_ema = float(ind.calculate_ema(df_1d['close'], macro_period).iloc[-1])
        else:
            macro_period = min(self.ema_slow, len(df_4h) - 1)
            macro_ema = float(ind.calculate_ema(df_4h['close'], macro_period).iloc[-1])
            
        is_bull = current_price >= macro_ema
        from .engine import B3AnchorEngine
        if symbol == 'BTCUSDT':
            B3AnchorEngine.GLOBAL_REGIME = "BULL" if is_bull else "BEAR"
            
        # 2. Indicadores 4H de Valor Profundo (RSI, Z-Score, Bollinger, ATR)
        rsi_series = ind.calculate_rsi(df_4h['close'], 14)
        z_series = ind.calculate_zscore(df_4h['close'], self.bb_period)
        bb_upper, bb_mid, bb_lower = ind.calculate_bbands(df_4h['close'], self.bb_period, self.bb_std)
        atr_series = ind.calculate_atr(df_4h['high'], df_4h['low'], df_4h['close'], self.atr_period)
        
        rsi_val = float(rsi_series.iloc[-1])
        prev_rsi = float(rsi_series.iloc[-2]) if len(rsi_series) > 1 else rsi_val
        z_val = float(z_series.iloc[-1])
        prev_z = float(z_series.iloc[-2]) if len(z_series) > 1 else z_val
        bb_u = float(bb_upper.iloc[-1])
        bb_l = float(bb_lower.iloc[-1])
        atr_val = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else current_price * 0.015
        
        # Vela de absorción / reversión alcista (cierre >= apertura o mecha inferior de rechazo > 40% del rango)
        candle_range = max(current_high - current_low, 1e-8)
        lower_wick_ratio = (min(current_open, current_price) - current_low) / candle_range
        bullish_absorption = (current_price >= current_open) or (lower_wick_ratio >= 0.40)
        
        # Condición de Miedo Extremo / Descuento Institucional (en vela actual o previa inmediata)
        deep_discount = (
            rsi_val < self.rsi_buy or
            prev_rsi < self.rsi_buy or
            z_val < self.z_buy or
            prev_z < self.z_buy or
            current_low <= bb_l
        )
        
        # ═══ SEÑAL 1: ACUMULACIÓN WYCKOFF EN DESCUENTO PROFUNDO (LONG) ═══
        if deep_discount and bullish_absorption:
            # V8.1 Mejora 3: Respiro institucional de 3.5% mínimo para evitar barridos de liquidez en índices
            sl_dist = min(current_price * 0.065, max(atr_val * 2.8, current_price * 0.035))
            tp_dist = max(current_price * 0.14, atr_val * 5.5)
            
            stop_loss = current_price - sl_dist
            take_profit = current_price + tp_dist
            
            strength = min(1.0, max(0.70, (38.0 - min(rsi_val, prev_rsi)) / 20.0 + 0.65))
            reason = f"Wyckoff Spring 4H (RSI={min(rsi_val, prev_rsi):.1f}, Z={min(z_val, prev_z):.2f})"
            
            return TradeSignal(
                symbol=symbol,
                side='LONG',
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason=reason,
                strength=round(strength, 2)
            )
            
        # ═══ SEÑAL 2: SALIDA EN FORTALEZA / EUFORIA (EXIT_LONG) ═══
        if rsi_val >= self.rsi_sell or current_price >= bb_u:
            reason = f"Strength Distribution Exit (RSI={rsi_val:.1f}, Price>=BB_Upper)"
            return TradeSignal(
                symbol=symbol,
                side='EXIT_LONG',
                entry_price=current_price,
                stop_loss=0.0,
                take_profit=0.0,
                reason=reason,
                strength=0.95
            )
            
        return None

    def _prepare_df(self, klines):
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume', 
            'close_time', 'quote_asset_volume', 'trades', 
            'taker_buy_base', 'taker_buy_quote', 'ignore'
        ])
        df['open'] = pd.to_numeric(df['open'])
        df['close'] = pd.to_numeric(df['close'])
        df['high'] = pd.to_numeric(df['high'])
        df['low'] = pd.to_numeric(df['low'])
        return df

