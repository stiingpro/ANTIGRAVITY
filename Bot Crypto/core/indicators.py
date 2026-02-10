import pandas as pd
import numpy as np
from typing import List, Tuple, Union

def calculate_ema(data: Union[List[float], pd.Series], period: int) -> pd.Series:
    """Exponential Moving Average (EMA)."""
    if isinstance(data, list):
        data = pd.Series(data)
    return data.ewm(span=period, adjust=False).mean()

def calculate_sma(data: Union[List[float], pd.Series], period: int) -> pd.Series:
    """Simple Moving Average (SMA)."""
    if isinstance(data, list):
        data = pd.Series(data)
    return data.rolling(window=period).mean()

def calculate_rsi(data: Union[List[float], pd.Series], period: int = 14) -> pd.Series:
    """Relative Strength Index (RSI)."""
    if isinstance(data, list):
        data = pd.Series(data)
    
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    # Use exponential moving average for wilder's RSI if needed, but simple rolling is robust enough for now
    # Or mimic standard RSI:
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range (ATR)."""
    h_l = high - low
    h_pc = (high - close.shift(1)).abs()
    l_pc = (low - close.shift(1)).abs()
    
    tr = pd.concat([h_l, h_pc, l_pc], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    return atr

def calculate_bbands(data: pd.Series, period: int = 20, std: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Bollinger Bands. Returns (Upper, Middle, Lower)."""
    ma = data.rolling(window=period).mean()
    sigma = data.rolling(window=period).std()
    upper = ma + (sigma * std)
    lower = ma - (sigma * std)
    return upper, ma, lower

def calculate_vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    """Volume Weighted Average Price (VWAP)."""
    tp = (high + low + close) / 3
    vwap = (tp * volume).cumsum() / volume.cumsum()
    return vwap
