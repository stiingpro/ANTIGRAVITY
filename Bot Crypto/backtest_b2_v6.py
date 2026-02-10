"""
B2_RESILIENCE V6 — Dual-Timeframe EMA Crossover
================================================
Ejecución: EMA 20/50 cruce en 1H
Dirección: EMA 200 filtro en 4H
Riesgo: SL dinámico ATR(4H) + RSI divergence exit
Activos: BTC, ETH, SOL, AVAX, LINK, DOT

Fase A: Optimización Walk-Forward 2023-2026
Fase B: Cámara de Tortura 2020-2026

Target: 0.9508% diario | 3x-5x leverage | $1M en 730 días

Ejecutar: py backtest_b2_v6.py
"""

import os
import sys
import json
import math
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s │ %(levelname)-8s │ %(message)s'
)
logger = logging.getLogger('B2_V6')


# ============================================================
# DATA MODELS
# ============================================================

class Side(Enum):
    LONG = 'BUY'
    SHORT = 'SELL'


@dataclass
class Candle:
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    @property
    def dt(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp / 1000)


@dataclass
class Trade:
    symbol: str
    side: Side
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    quantity: float
    entry_time: datetime
    exit_time: datetime
    exit_reason: str
    pnl_usd: float = 0.0
    pnl_pct: float = 0.0
    duration_hours: float = 0.0
    strength: float = 0.0
    reason: str = ''


@dataclass
class BacktestResult:
    symbol: str
    period: str
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl_usd: float = 0.0
    total_pnl_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win_usd: float = 0.0
    avg_loss_usd: float = 0.0
    avg_rr_ratio: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    avg_trade_duration_h: float = 0.0
    sharpe_ratio: float = 0.0
    recovery_factor: float = 0.0
    trades: List[Trade] = field(default_factory=list)


# ============================================================
# DATA LOADERS (1H + 4H)
# ============================================================

class DualTimeframeLoader:
    """
    Descarga datos 1H y 4H desde Binance.
    1H para señales de ejecución, 4H para filtro macro.
    """
    
    CACHE_DIR = os.path.join(os.path.dirname(__file__), 'backtest_data')
    
    def __init__(self):
        os.makedirs(self.CACHE_DIR, exist_ok=True)
    
    def load(self, symbol: str, start_date: str, end_date: str, 
             interval: str = '1h') -> List[Candle]:
        """Cargar datos históricos con caché."""
        cache_file = os.path.join(
            self.CACHE_DIR,
            f"{symbol}_{interval}_{start_date}_{end_date}.json"
        )
        
        if os.path.exists(cache_file):
            logger.info(f"  📁 Caché: {symbol} ({interval})")
            with open(cache_file, 'r') as f:
                raw = json.load(f)
            return [Candle(
                timestamp=k[0], open=float(k[1]), high=float(k[2]),
                low=float(k[3]), close=float(k[4]), volume=float(k[5])
            ) for k in raw]
        
        logger.info(f"  📥 Descargando {symbol} {interval} ({start_date} → {end_date})...")
        klines = self._download(symbol, start_date, end_date, interval)
        
        with open(cache_file, 'w') as f:
            json.dump(klines, f)
        
        return [Candle(
            timestamp=k[0], open=float(k[1]), high=float(k[2]),
            low=float(k[3]), close=float(k[4]), volume=float(k[5])
        ) for k in klines]
    
    def _download(self, symbol: str, start_date: str, end_date: str, 
                  interval: str) -> List:
        """Descargar klines de Binance."""
        import urllib.request
        import urllib.parse
        
        all_klines = []
        start_ms = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp() * 1000)
        end_ms = int(datetime.strptime(end_date, '%Y-%m-%d').timestamp() * 1000)
        current = start_ms
        
        while current < end_ms:
            params = urllib.parse.urlencode({
                'symbol': symbol,
                'interval': interval,
                'startTime': current,
                'endTime': end_ms,
                'limit': 1000
            })
            url = f"https://fapi.binance.com/fapi/v1/klines?{params}"
            
            try:
                req = urllib.request.Request(url)
                req.add_header('User-Agent', 'Mozilla/5.0')
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read())
                
                if not data:
                    break
                
                all_klines.extend(data)
                current = data[-1][0] + 1
                
                pct = min(100, (current - start_ms) / (end_ms - start_ms) * 100)
                sys.stdout.write(f"\r    {symbol} {interval}: {pct:.0f}% ({len(all_klines)} velas)")
                sys.stdout.flush()
                time.sleep(0.2)
                
            except Exception as e:
                logger.warning(f"  ⚠️ Error: {symbol} {interval}: {e}")
                time.sleep(2)
                continue
        
        print()
        return all_klines


# ============================================================
# V6 STRATEGY: Dual-Timeframe EMA Crossover + RSI Divergence
# ============================================================

class V6Strategy:
    """
    Estrategia V6 Dual-Timeframe.
    
    EJECUCIÓN (1H):
    - EMA(20) cruza EMA(50) ↑ = LONG signal
    - EMA(20) cruza EMA(50) ↓ = SHORT signal
    - RSI(14) para confirmar momentum
    
    DIRECCIÓN MACRO (4H):
    - Price > EMA(200) = Solo LONG permitido
    - Price < EMA(200) = Solo SHORT permitido
    - ATR(14) en 4H para sizing de SL/TP
    
    SALIDA:
    - SL dinámico basado en ATR(4H)
    - RSI divergencia como señal de salida anticipada
    """
    
    def __init__(self, config: Dict):
        self.cfg = config
        
        # EMA períodos (1H)
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
        
        # ATR (4H)
        self.atr_period = config.get('atr_period', 14)
        self.sl_atr_mult = config.get('sl_atr_mult', 2.0)
        self.tp_atr_mult = config.get('tp_atr_mult', 4.0)
        
        # Filtros
        self.min_strength = config.get('min_strength', 0.55)
        self.vol_threshold = config.get('vol_threshold', 0.8)
        self.volume_avg_period = 20
        
        # RSI divergence
        self.rsi_div_lookback = config.get('rsi_div_lookback', 5)
    
    def analyze(self, candles_1h: List[Candle], candles_4h: List[Candle], 
                symbol: str) -> Optional[Dict]:
        """
        Analizar datos duales (1H + 4H) y generar señal.
        """
        if len(candles_1h) < self.ema_slow + 5:
            return None
        if len(candles_4h) < self.ema_macro + 5:
            return None
        
        # === 4H DATOS (Dirección Macro) ===
        closes_4h = [c.close for c in candles_4h]
        highs_4h = [c.high for c in candles_4h]
        lows_4h = [c.low for c in candles_4h]
        
        ema200_4h = self._ema(closes_4h, self.ema_macro)
        atr_4h = self._atr(highs_4h, lows_4h, closes_4h, self.atr_period)
        price_4h = closes_4h[-1]
        
        # Macro direction
        macro_bullish = price_4h > ema200_4h
        macro_bearish = price_4h < ema200_4h
        
        # Distancia % al EMA200 (fuerza de tendencia macro)
        macro_dist_pct = abs(price_4h - ema200_4h) / ema200_4h * 100
        
        # === 1H DATOS (Ejecución) ===
        closes_1h = [c.close for c in candles_1h]
        highs_1h = [c.high for c in candles_1h]
        lows_1h = [c.low for c in candles_1h]
        volumes_1h = [c.volume for c in candles_1h]
        
        price = closes_1h[-1]
        
        # EMA crossover (1H)
        ema20 = self._ema(closes_1h, self.ema_fast)
        ema50 = self._ema(closes_1h, self.ema_slow)
        prev_ema20 = self._ema(closes_1h[:-1], self.ema_fast)
        prev_ema50 = self._ema(closes_1h[:-1], self.ema_slow)
        
        bullish_cross = prev_ema20 <= prev_ema50 and ema20 > ema50
        bearish_cross = prev_ema20 >= prev_ema50 and ema20 < ema50
        ema_above = ema20 > ema50
        ema_below = ema20 < ema50
        
        # RSI (1H)
        rsi = self._rsi(closes_1h, self.rsi_period)
        
        # Volume (1H)
        vol_avg = sum(volumes_1h[-self.volume_avg_period:]) / self.volume_avg_period
        vol_current = volumes_1h[-1]
        vol_confirm = vol_current > vol_avg * self.vol_threshold
        
        # RSI divergence check (para salidas)
        rsi_div_bearish = self._check_rsi_divergence(closes_1h, 'bearish')
        rsi_div_bullish = self._check_rsi_divergence(closes_1h, 'bullish')
        
        # SL/TP dinámico con ATR de 4H
        sl_dist = atr_4h * self.sl_atr_mult if atr_4h > 0 else price * 0.02
        tp_dist = atr_4h * self.tp_atr_mult if atr_4h > 0 else price * 0.04
        
        # ========== LONG SCORE ==========
        long_score = 0.0
        long_reasons = []
        
        if macro_bullish:  # Filtro macro obligatorio
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
            
            # Bonus por distancia macro (tendencia fuerte)
            if macro_dist_pct > 2.0:
                long_score += 0.15
                long_reasons.append(f">EMA200({macro_dist_pct:.1f}%)")
            elif macro_dist_pct > 0.5:
                long_score += 0.10
                long_reasons.append(">EMA200")
            
            # Penalty por RSI divergencia bearish
            if rsi_div_bearish:
                long_score -= 0.20
                long_reasons.append("RSIdiv↓")
        
        # ========== SHORT SCORE ==========
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
                short_reasons.append("RSIdiv↑")
        
        # ========== GENERAR SEÑAL ==========
        if long_score >= self.min_strength and long_score > short_score:
            return {
                'side': Side.LONG,
                'strength': min(long_score, 1.0),
                'entry': price,
                'sl': price - sl_dist,
                'tp': price + tp_dist,
                'reason': ' + '.join(long_reasons),
                'atr': atr_4h
            }
        
        if short_score >= self.min_strength and short_score > long_score:
            return {
                'side': Side.SHORT,
                'strength': min(short_score, 1.0),
                'entry': price,
                'sl': price + sl_dist,
                'tp': price - tp_dist,
                'reason': ' + '.join(short_reasons),
                'atr': atr_4h
            }
        
        return None
    
    def check_rsi_exit(self, candles_1h: List[Candle], side: Side) -> bool:
        """Verificar si hay divergencia RSI para salida anticipada."""
        if len(candles_1h) < self.rsi_div_lookback + self.rsi_period + 2:
            return False
        
        closes = [c.close for c in candles_1h]
        
        if side == Side.LONG:
            return self._check_rsi_divergence(closes, 'bearish')
        else:
            return self._check_rsi_divergence(closes, 'bullish')
    
    def _check_rsi_divergence(self, closes: List[float], div_type: str) -> bool:
        """
        Detectar divergencia RSI.
        Bearish div: Precio hace higher high pero RSI hace lower high
        Bullish div: Precio hace lower low pero RSI hace higher low
        """
        n = self.rsi_div_lookback
        if len(closes) < n + self.rsi_period + 2:
            return False
        
        # RSI de las últimas n velas
        rsi_values = []
        for i in range(n):
            idx = len(closes) - n + i
            rsi_val = self._rsi(closes[:idx+1], self.rsi_period)
            rsi_values.append(rsi_val)
        
        recent_closes = closes[-n:]
        
        if div_type == 'bearish':
            # Precio sube, RSI baja
            price_rising = recent_closes[-1] > recent_closes[0]
            rsi_falling = rsi_values[-1] < rsi_values[0]
            return price_rising and rsi_falling and rsi_values[-1] > 60
        
        elif div_type == 'bullish':
            # Precio baja, RSI sube
            price_falling = recent_closes[-1] < recent_closes[0]
            rsi_rising = rsi_values[-1] > rsi_values[0]
            return price_falling and rsi_rising and rsi_values[-1] < 40
        
        return False
    
    # ===== INDICADORES =====
    
    def _ema(self, data, period):
        if len(data) < period:
            return sum(data) / len(data) if data else 0
        mult = 2 / (period + 1)
        ema = sum(data[:period]) / period
        for val in data[period:]:
            ema = (val * mult) + (ema * (1 - mult))
        return ema
    
    def _rsi(self, closes, period):
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
    
    def _atr(self, highs, lows, closes, period):
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


# ============================================================
# BACKTESTING ENGINE (Dual-Timeframe)
# ============================================================

class BacktestEngineV6:
    """
    Motor de backtesting dual-timeframe.
    Combina señales 1H con filtro macro 4H.
    """
    
    def __init__(self, config: Dict):
        self.cfg = config
        self.initial_balance = config.get('initial_balance', 1000.0)
        self.position_size_pct = config.get('position_size_pct', 3.0)
        self.leverage = config.get('leverage', 5)
        self.commission_pct = config.get('commission_pct', 0.04)
        self.cooldown_candles = config.get('cooldown_candles', 8)
        self.max_consecutive_losses = config.get('max_consecutive_losses', 3)
        self.label = config.get('label', 'V6')
        
        self.strategy = V6Strategy(config)
        self.loader = DualTimeframeLoader()
    
    def run(self, symbols: List[str], start_date: str, end_date: str,
            period_label: str = '') -> Dict[str, BacktestResult]:
        """Ejecutar backtest dual-timeframe."""
        
        logger.info("=" * 70)
        logger.info(f"⚡ BACKTESTING V6 DUAL-TIMEFRAME [{self.label}]")
        logger.info(f"   Periodo: {start_date} → {end_date} {period_label}")
        logger.info(f"   Pares: {', '.join(symbols)}")
        logger.info(f"   Balance: ${self.initial_balance:,.0f} │ Pos: {self.position_size_pct}%")
        logger.info(f"   EMA: {self.cfg.get('ema_fast',20)}/{self.cfg.get('ema_slow',50)} (1H) + {self.cfg.get('ema_macro',200)} (4H)")
        logger.info(f"   SL: {self.cfg.get('sl_atr_mult',2.0)}x ATR(4H) │ TP: {self.cfg.get('tp_atr_mult',4.0)}x ATR(4H)")
        logger.info(f"   Leverage: {self.leverage}x │ Fee: {self.commission_pct}%")
        logger.info(f"   Min Strength: {self.cfg.get('min_strength',0.55)} │ Cooldown: {self.cooldown_candles}h")
        logger.info("=" * 70)
        
        # Descargar datos duales
        logger.info("\n📥 Descargando datos duales (1H + 4H)...")
        data_1h = {}
        data_4h = {}
        
        for sym in symbols:
            c_1h = self.loader.load(sym, start_date, end_date, '1h')
            c_4h = self.loader.load(sym, start_date, end_date, '4h')
            if c_1h and c_4h:
                data_1h[sym] = c_1h
                data_4h[sym] = c_4h
                logger.info(f"  ✅ {sym}: {len(c_1h)} (1H) + {len(c_4h)} (4H)")
        
        # Backtest por símbolo
        logger.info("\n🔄 Ejecutando simulación V6...")
        results = {}
        
        for sym in data_1h:
            result = self._backtest_symbol(sym, data_1h[sym], data_4h[sym])
            results[sym] = result
            self._print_symbol_result(result)
        
        # Portfolio
        logger.info("\n" + "=" * 70)
        self._print_portfolio_summary(results)
        
        return results
    
    def _backtest_symbol(self, symbol: str, candles_1h: List[Candle], 
                         candles_4h: List[Candle]) -> BacktestResult:
        """Backtest dual-timeframe para un símbolo."""
        balance = self.initial_balance
        peak_balance = balance
        max_drawdown = 0
        
        trades = []
        open_trade = None
        lookback_1h = 55
        lookback_4h = 205
        cooldown_remaining = 0
        consecutive_losses = 0
        
        equity_curve = []
        
        # Mapear 4H a timestamps para sincronizar
        ts_4h = {int(c.timestamp): i for i, c in enumerate(candles_4h)}
        
        for i in range(lookback_1h, len(candles_1h)):
            current_1h = candles_1h[i]
            window_1h = candles_1h[max(0, i - lookback_1h):i + 1]
            
            # Encontrar la ventana 4H correspondiente
            current_ts = current_1h.timestamp
            # Buscar la vela 4H más reciente antes del timestamp actual
            best_4h_idx = 0
            for ts, idx in ts_4h.items():
                if ts <= current_ts:
                    best_4h_idx = max(best_4h_idx, idx)
            
            if best_4h_idx < lookback_4h:
                equity_curve.append(balance)
                continue
            
            window_4h = candles_4h[max(0, best_4h_idx - lookback_4h):best_4h_idx + 1]
            
            # Si hay trade abierto, verificar SL/TP + RSI exit
            if open_trade:
                # RSI divergence exit
                rsi_exit = self.strategy.check_rsi_exit(window_1h, open_trade['side'])
                
                hit = self._check_sl_tp(open_trade, current_1h)
                
                if rsi_exit and not hit:
                    # RSI divergence exit anticipada
                    exit_price = current_1h.close
                    trade = self._close_trade(
                        open_trade, exit_price, 'RSI_DIV',
                        current_1h.dt, balance
                    )
                    trades.append(trade)
                    balance += trade.pnl_usd
                    if trade.pnl_usd < 0:
                        consecutive_losses += 1
                    else:
                        consecutive_losses = 0
                    peak_balance = max(peak_balance, balance)
                    dd = (peak_balance - balance) / peak_balance * 100 if peak_balance > 0 else 0
                    max_drawdown = max(max_drawdown, dd)
                    open_trade = None
                    cooldown_remaining = self.cooldown_candles
                
                elif hit:
                    exit_price, exit_reason = hit
                    trade = self._close_trade(
                        open_trade, exit_price, exit_reason,
                        current_1h.dt, balance
                    )
                    trades.append(trade)
                    balance += trade.pnl_usd
                    if trade.pnl_usd < 0:
                        consecutive_losses += 1
                    else:
                        consecutive_losses = 0
                    peak_balance = max(peak_balance, balance)
                    dd = (peak_balance - balance) / peak_balance * 100 if peak_balance > 0 else 0
                    max_drawdown = max(max_drawdown, dd)
                    open_trade = None
                    cooldown_remaining = self.cooldown_candles
            
            # Cooldown
            if cooldown_remaining > 0:
                cooldown_remaining -= 1
            
            # Pausa por pérdidas consecutivas
            if consecutive_losses >= self.max_consecutive_losses:
                cooldown_remaining = max(cooldown_remaining, 24)
                consecutive_losses = 0
            
            # Buscar nueva señal
            if not open_trade and cooldown_remaining <= 0 and balance > 0:
                signal = self.strategy.analyze(window_1h, window_4h, symbol)
                
                if signal:
                    # Position size ajustado por leverage
                    margin = balance * (self.position_size_pct / 100)
                    
                    # Leverage dinámico basado en fuerza de señal
                    effective_leverage = self._dynamic_leverage(signal['strength'])
                    notional = margin * effective_leverage
                    quantity = notional / signal['entry']
                    
                    open_trade = {
                        'symbol': symbol,
                        'side': signal['side'],
                        'entry_price': signal['entry'],
                        'sl': signal['sl'],
                        'tp': signal['tp'],
                        'quantity': quantity,
                        'entry_time': current_1h.dt,
                        'strength': signal['strength'],
                        'reason': signal['reason'],
                        'leverage': effective_leverage
                    }
            
            equity_curve.append(balance)
        
        # Cerrar trade al final
        if open_trade:
            final_price = candles_1h[-1].close
            trade = self._close_trade(
                open_trade, final_price, 'END',
                candles_1h[-1].dt, balance
            )
            trades.append(trade)
            balance += trade.pnl_usd
        
        return self._compute_metrics(symbol, trades, balance, max_drawdown, equity_curve)
    
    def _dynamic_leverage(self, strength: float) -> int:
        """Leverage dinámico 3x-5x basado en fuerza de señal."""
        min_lev = self.cfg.get('min_leverage', 3)
        max_lev = self.cfg.get('max_leverage', 5)
        
        if strength >= 0.80:
            return max_lev       # 5x para señales fuertes
        elif strength >= 0.65:
            return min(max_lev, 4)  # 4x
        else:
            return min_lev       # 3x para señales normales
    
    def _check_sl_tp(self, trade: Dict, candle: Candle) -> Optional[Tuple[float, str]]:
        if trade['side'] == Side.LONG:
            if candle.low <= trade['sl']:
                return (trade['sl'], 'SL')
            if candle.high >= trade['tp']:
                return (trade['tp'], 'TP')
        else:
            if candle.high >= trade['sl']:
                return (trade['sl'], 'SL')
            if candle.low <= trade['tp']:
                return (trade['tp'], 'TP')
        return None
    
    def _close_trade(self, trade: Dict, exit_price: float, reason: str,
                     exit_time: datetime, balance: float) -> Trade:
        qty = trade['quantity']
        entry = trade['entry_price']
        
        if trade['side'] == Side.LONG:
            pnl_raw = (exit_price - entry) * qty
        else:
            pnl_raw = (entry - exit_price) * qty
        
        commission = (entry * qty + exit_price * qty) * (self.commission_pct / 100)
        pnl_usd = pnl_raw - commission
        
        margin = balance * (self.position_size_pct / 100)
        pnl_pct = (pnl_usd / margin * 100) if margin > 0 else 0
        
        duration = (exit_time - trade['entry_time']).total_seconds() / 3600
        
        return Trade(
            symbol=trade['symbol'],
            side=trade['side'],
            entry_price=entry,
            exit_price=exit_price,
            stop_loss=trade['sl'],
            take_profit=trade['tp'],
            quantity=qty,
            entry_time=trade['entry_time'],
            exit_time=exit_time,
            exit_reason=reason,
            pnl_usd=pnl_usd,
            pnl_pct=pnl_pct,
            duration_hours=duration,
            strength=trade['strength'],
            reason=trade['reason']
        )
    
    def _compute_metrics(self, symbol: str, trades: List[Trade], 
                         final_balance: float, max_drawdown: float,
                         equity_curve: List[float]) -> BacktestResult:
        result = BacktestResult(symbol=symbol, period=self.label, trades=trades)
        result.total_trades = len(trades)
        
        if not trades:
            return result
        
        winners = [t for t in trades if t.pnl_usd > 0]
        losers = [t for t in trades if t.pnl_usd <= 0]
        
        result.winning_trades = len(winners)
        result.losing_trades = len(losers)
        result.total_pnl_usd = sum(t.pnl_usd for t in trades)
        result.total_pnl_pct = (result.total_pnl_usd / self.initial_balance) * 100
        result.max_drawdown_pct = max_drawdown
        result.win_rate = (len(winners) / len(trades) * 100) if trades else 0
        
        total_wins = sum(t.pnl_usd for t in winners) if winners else 0
        total_losses = abs(sum(t.pnl_usd for t in losers)) if losers else 0
        result.profit_factor = (total_wins / total_losses) if total_losses > 0 else float('inf')
        
        result.avg_win_usd = (total_wins / len(winners)) if winners else 0
        result.avg_loss_usd = (total_losses / len(losers)) if losers else 0
        
        if result.avg_loss_usd > 0:
            result.avg_rr_ratio = result.avg_win_usd / result.avg_loss_usd
        
        result.avg_trade_duration_h = (
            sum(t.duration_hours for t in trades) / len(trades)
        ) if trades else 0
        
        # Recovery factor = Total PnL / Max DD
        if max_drawdown > 0:
            max_dd_usd = self.initial_balance * max_drawdown / 100
            result.recovery_factor = result.total_pnl_usd / max_dd_usd if max_dd_usd > 0 else 0
        
        # Rachas
        cw, cl = 0, 0
        for t in trades:
            if t.pnl_usd > 0:
                cw += 1; cl = 0
                result.max_consecutive_wins = max(result.max_consecutive_wins, cw)
            else:
                cl += 1; cw = 0
                result.max_consecutive_losses = max(result.max_consecutive_losses, cl)
        
        # Sharpe Ratio
        if len(trades) > 1:
            returns = [t.pnl_pct for t in trades]
            avg_ret = sum(returns) / len(returns)
            std_ret = math.sqrt(sum((r - avg_ret)**2 for r in returns) / (len(returns) - 1))
            if std_ret > 0:
                tpy = 365 * 24 / (result.avg_trade_duration_h or 24)
                result.sharpe_ratio = (avg_ret / std_ret) * math.sqrt(min(tpy, 365))
        
        return result
    
    def _print_symbol_result(self, r: BacktestResult):
        emoji = '✅' if r.total_pnl_usd > 0 else '❌'
        logger.info(
            f"\n  {emoji} {r.symbol:10s} │ "
            f"Trades={r.total_trades:4d} │ "
            f"Win={r.win_rate:5.1f}% │ "
            f"PnL=${r.total_pnl_usd:>+10,.2f} ({r.total_pnl_pct:>+6.1f}%) │ "
            f"PF={r.profit_factor:.2f} │ "
            f"MaxDD={r.max_drawdown_pct:.1f}% │ "
            f"Sharpe={r.sharpe_ratio:.2f} │ "
            f"RecF={r.recovery_factor:.2f}"
        )
    
    def _print_portfolio_summary(self, results: Dict[str, BacktestResult]):
        total_trades = sum(r.total_trades for r in results.values())
        total_wins = sum(r.winning_trades for r in results.values())
        total_pnl = sum(r.total_pnl_usd for r in results.values())
        
        all_trades = []
        for r in results.values():
            all_trades.extend(r.trades)
        
        total_win_usd = sum(t.pnl_usd for t in all_trades if t.pnl_usd > 0)
        total_loss_usd = abs(sum(t.pnl_usd for t in all_trades if t.pnl_usd <= 0))
        
        win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
        pf = (total_win_usd / total_loss_usd) if total_loss_usd > 0 else 0
        pnl_pct = (total_pnl / self.initial_balance) * 100
        max_dd = max(r.max_drawdown_pct for r in results.values()) if results else 0
        final = self.initial_balance + total_pnl
        
        logger.info(f"⚡ RESUMEN PORTFOLIO V6 [{self.label}]")
        logger.info("=" * 70)
        logger.info(f"  💰 Balance inicial:    ${self.initial_balance:>12,.2f}")
        logger.info(f"  💰 Balance final:      ${final:>12,.2f}")
        logger.info(f"  📈 PnL Total:          ${total_pnl:>+12,.2f} ({pnl_pct:>+.1f}%)")
        logger.info(f"  📊 Total trades:       {total_trades:>8d}")
        logger.info(f"  ✅ Ganadores:          {total_wins:>8d}")
        logger.info(f"  ❌ Perdedores:         {total_trades - total_wins:>8d}")
        logger.info(f"  🎯 Win Rate:           {win_rate:>7.1f}%")
        logger.info(f"  📐 Profit Factor:      {pf:>8.2f}")
        logger.info(f"  📉 Max Drawdown:       {max_dd:>7.1f}%")
        if total_wins > 0:
            logger.info(f"  💵 Avg Win:            ${total_win_usd / total_wins:>+10,.2f}")
        if total_trades > total_wins > 0:
            logger.info(f"  💸 Avg Loss:           ${-total_loss_usd / (total_trades - total_wins):>+10,.2f}")
        logger.info("=" * 70)
        
        # Ranking
        logger.info("\n🏆 RANKING POR SÍMBOLO:")
        for i, r in enumerate(sorted(results.values(), key=lambda x: x.total_pnl_usd, reverse=True), 1):
            emoji = '🥇🥈🥉'[i-1] if i <= 3 else f'#{i}'
            bar_len = max(0, int(r.total_pnl_pct / 5)) if r.total_pnl_pct > 0 else 0
            logger.info(
                f"  {emoji} {r.symbol:10s} │ "
                f"PnL=${r.total_pnl_usd:>+10,.2f} │ "
                f"Win={r.win_rate:5.1f}% │ "
                f"PF={r.profit_factor:.2f} │ {'█' * min(bar_len, 30)}"
            )
        
        # PnL Mensual
        logger.info("\n📅 PnL MENSUAL:")
        monthly = {}
        for t in sorted(all_trades, key=lambda x: x.entry_time):
            mk = t.entry_time.strftime('%Y-%m')
            monthly[mk] = monthly.get(mk, 0) + t.pnl_usd
        
        for m, pnl in sorted(monthly.items()):
            bar = ('🟢' if pnl >= 0 else '🔴') * min(int(abs(pnl) / 10), 20)
            logger.info(f"  {m} │ ${pnl:>+10,.2f} │ {bar}")


# ============================================================
# MAIN — FASE A (Optimización) + FASE B (Cámara de Tortura)
# ============================================================

def portfolio_stats(results, initial):
    """Calcular estadísticas de portfolio."""
    total_trades = sum(r.total_trades for r in results.values())
    total_wins = sum(r.winning_trades for r in results.values())
    total_pnl = sum(r.total_pnl_usd for r in results.values())
    wr = (total_wins / total_trades * 100) if total_trades > 0 else 0
    all_t = [t for r in results.values() for t in r.trades]
    tw = sum(t.pnl_usd for t in all_t if t.pnl_usd > 0)
    tl = abs(sum(t.pnl_usd for t in all_t if t.pnl_usd <= 0))
    pf = tw / tl if tl > 0 else 0
    dd = max(r.max_drawdown_pct for r in results.values()) if results else 0
    final = initial + total_pnl
    roi = ((final - initial) / initial) * 100
    
    # Sharpe promedio ponderado
    sharpe_vals = [r.sharpe_ratio for r in results.values() if r.sharpe_ratio != 0]
    avg_sharpe = sum(sharpe_vals) / len(sharpe_vals) if sharpe_vals else 0
    
    # Recovery factor
    rec_vals = [r.recovery_factor for r in results.values() if r.recovery_factor != 0]
    avg_rec = sum(rec_vals) / len(rec_vals) if rec_vals else 0
    
    # Probabilidad de supervivencia (heurística)
    survival = 100.0
    if dd > 50:
        survival = 10.0
    elif dd > 30:
        survival = 40.0
    elif dd > 15:
        survival = 65.0
    elif dd > 10:
        survival = 80.0
    elif dd > 5:
        survival = 90.0
    
    if pf < 0.8:
        survival *= 0.5
    elif pf < 1.0:
        survival *= 0.7
    elif pf > 1.5:
        survival = min(99, survival * 1.1)
    
    return {
        'trades': total_trades, 'wr': wr, 'pnl': total_pnl,
        'pf': pf, 'dd': dd, 'final': final, 'roi': roi,
        'sharpe': avg_sharpe, 'recovery': avg_rec, 'survival': survival
    }


if __name__ == '__main__':
    
    SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'AVAXUSDT', 'LINKUSDT', 'DOTUSDT']
    INITIAL = 1000.0
    
    # ============================================
    # FASE A: Optimización Walk-Forward 2023-2026
    # ============================================
    PHASE_A_START = '2023-01-01'
    PHASE_A_END = '2026-02-10'
    
    logger.info("\n" + "🔬" * 35)
    logger.info("   FASE A: OPTIMIZACIÓN WALK-FORWARD (2023-2026)")
    logger.info("🔬" * 35)
    
    # Configuración V6 optimizada
    v6_config = {
        'label': 'V6-DualTF',
        'initial_balance': INITIAL,
        
        # EMA
        'ema_fast': 20,
        'ema_slow': 50,
        'ema_macro': 200,
        
        # RSI
        'rsi_period': 14,
        'rsi_long_min': 40,
        'rsi_long_max': 70,
        'rsi_short_min': 30,
        'rsi_short_max': 60,
        'rsi_div_lookback': 5,
        
        # ATR / SL / TP
        'atr_period': 14,
        'sl_atr_mult': 2.0,
        'tp_atr_mult': 4.0,
        
        # Position & Risk
        'position_size_pct': 3.0,
        'leverage': 5,
        'min_leverage': 3,
        'max_leverage': 5,
        'commission_pct': 0.04,
        'cooldown_candles': 6,
        'max_consecutive_losses': 3,
        
        # Signal
        'min_strength': 0.55,
        'vol_threshold': 0.8,
    }
    
    engine_a = BacktestEngineV6(v6_config)
    results_a = engine_a.run(
        symbols=SYMBOLS, 
        start_date=PHASE_A_START, 
        end_date=PHASE_A_END,
        period_label='[FASE A - Optimización]'
    )
    stats_a = portfolio_stats(results_a, INITIAL)
    
    # Guardar reporte Fase A
    report_a = {
        'phase': 'A - Optimization Walk-Forward',
        'period': f'{PHASE_A_START} to {PHASE_A_END}',
        'config': v6_config,
        'stats': stats_a,
        'timestamp': datetime.now().isoformat()
    }
    report_a_path = os.path.join(
        os.path.dirname(__file__),
        f'backtest_v6_phaseA_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    )
    with open(report_a_path, 'w') as f:
        json.dump(report_a, f, indent=2, default=str)
    logger.info(f"\n📁 Reporte Fase A: {report_a_path}")
    
    # ============================================
    # FASE B: Cámara de Tortura 2020-2026
    # ============================================
    PHASE_B_START = '2020-01-01'
    PHASE_B_END = '2026-02-10'
    
    logger.info("\n" + "💀" * 35)
    logger.info("   FASE B: CÁMARA DE TORTURA (2020-2026)")
    logger.info("   COVID crash | Luna collapse | FTX implosion")
    logger.info("💀" * 35)
    
    # MISMA configuración, sin ajustes
    v6_config_b = dict(v6_config)
    v6_config_b['label'] = 'V6-TORTURE'
    
    engine_b = BacktestEngineV6(v6_config_b)
    results_b = engine_b.run(
        symbols=SYMBOLS,
        start_date=PHASE_B_START,
        end_date=PHASE_B_END,
        period_label='[FASE B - Cámara de Tortura]'
    )
    stats_b = portfolio_stats(results_b, INITIAL)
    
    # Guardar reporte Fase B
    report_b = {
        'phase': 'B - Torture Chamber',
        'period': f'{PHASE_B_START} to {PHASE_B_END}',
        'config': v6_config_b,
        'stats': stats_b,
        'timestamp': datetime.now().isoformat()
    }
    report_b_path = os.path.join(
        os.path.dirname(__file__),
        f'backtest_v6_phaseB_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    )
    with open(report_b_path, 'w') as f:
        json.dump(report_b, f, indent=2, default=str)
    logger.info(f"\n📁 Reporte Fase B: {report_b_path}")
    
    # ============================================
    # TABLA COMPARATIVA FINAL
    # ============================================
    logger.info("\n" + "=" * 100)
    logger.info("📊 TABLA COMPARATIVA: FASE A vs FASE B — FACTORES DE DECISIÓN")
    logger.info("=" * 100)
    
    logger.info(f"\n  {'Métrica':<30s} {'Fase A (2023-2026)':>20s} {'Fase B (2020-2026)':>20s}")
    logger.info(f"  {'━'*72}")
    logger.info(f"  {'Balance Inicial':<30s} ${INITIAL:>18,.2f} ${INITIAL:>18,.2f}")
    logger.info(f"  {'Balance Final':<30s} ${stats_a['final']:>18,.2f} ${stats_b['final']:>18,.2f}")
    logger.info(f"  {'ROI':<30s} {stats_a['roi']:>+17.1f}% {stats_b['roi']:>+17.1f}%")
    logger.info(f"  {'Total Trades':<30s} {stats_a['trades']:>18,d} {stats_b['trades']:>18,d}")
    logger.info(f"  {'Win Rate':<30s} {stats_a['wr']:>17.1f}% {stats_b['wr']:>17.1f}%")
    logger.info(f"  {'Profit Factor':<30s} {stats_a['pf']:>18.2f} {stats_b['pf']:>18.2f}")
    logger.info(f"  {'Max Drawdown':<30s} {stats_a['dd']:>17.1f}% {stats_b['dd']:>17.1f}%")
    logger.info(f"  {'Sharpe Ratio':<30s} {stats_a['sharpe']:>18.2f} {stats_b['sharpe']:>18.2f}")
    logger.info(f"  {'Recovery Factor':<30s} {stats_a['recovery']:>18.2f} {stats_b['recovery']:>18.2f}")
    logger.info(f"  {'Prob. Supervivencia':<30s} {stats_a['survival']:>17.0f}% {stats_b['survival']:>17.0f}%")
    logger.info(f"  {'━'*72}")
    
    # Veredicto
    logger.info("\n⚖️  VEREDICTO:")
    
    if stats_a['roi'] > 0 and stats_b['roi'] > 0:
        if stats_b['dd'] < 15:
            logger.info("  ✅ APROBADO: Rentable en ambas fases con drawdown aceptable")
        else:
            logger.info("  ⚠️ PRECAUCIÓN: Rentable pero drawdown alto en fase de estrés")
    elif stats_a['roi'] > 0:
        logger.info("  ⚠️ PARCIAL: Rentable en optimización pero no sobrevive al estrés")
    else:
        logger.info("  ❌ RECHAZADO: Estrategia no rentable en fase de optimización")
    
    # Target check
    daily_target = 0.9508
    if stats_a['trades'] > 0:
        all_trades_a = [t for r in results_a.values() for t in r.trades]
        if all_trades_a:
            first_trade = min(all_trades_a, key=lambda x: x.entry_time)
            last_trade = max(all_trades_a, key=lambda x: x.exit_time)
            total_days = (last_trade.exit_time - first_trade.entry_time).days
            if total_days > 0:
                actual_daily = (((stats_a['final'] / INITIAL) ** (1 / total_days)) - 1) * 100
                logger.info(f"\n  📈 Rendimiento diario real: {actual_daily:.4f}%")
                logger.info(f"  🎯 Target diario: {daily_target:.4f}%")
                logger.info(f"  {'✅' if actual_daily >= daily_target else '❌'} {'Alcanzado' if actual_daily >= daily_target else 'No alcanzado'}")
    
    logger.info("\n" + "=" * 100)
    
    # Desglose por activo
    logger.info("\n📊 DESGLOSE POR ACTIVO:")
    logger.info(f"\n  {'Símbolo':<10s} │ {'PnL (A)':>10s} │ {'WR (A)':>7s} │ {'PnL (B)':>10s} │ {'WR (B)':>7s} │ {'PF (A)':>6s} │ {'PF (B)':>6s}")
    logger.info(f"  {'━'*72}")
    
    for sym in SYMBOLS:
        ra = results_a.get(sym)
        rb = results_b.get(sym)
        if ra and rb:
            logger.info(
                f"  {sym:<10s} │ "
                f"${ra.total_pnl_usd:>+9,.2f} │ "
                f"{ra.win_rate:>5.1f}% │ "
                f"${rb.total_pnl_usd:>+9,.2f} │ "
                f"{rb.win_rate:>5.1f}% │ "
                f"{ra.profit_factor:>5.2f} │ "
                f"{rb.profit_factor:>5.2f}"
            )
    
    logger.info("=" * 100)
