"""
B2_RESILIENCE Backtesting Engine
=================================
Simulación histórica de la estrategia MRB (Mean Reversion Bands)
3 pares | 4H timeframe | Bollinger Bands + RSI | Perfil Conservador

Ejecutar: py backtest_b2.py
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
logger = logging.getLogger('BACKTEST_B2')


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
    exit_reason: str  # 'SL', 'TP', 'SIGNAL'
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
    trades: List[Trade] = field(default_factory=list)


# ============================================================
# HISTORICAL DATA DOWNLOADER (4H)
# ============================================================

class HistoricalDataLoader:
    """Descarga datos históricos 4H desde Binance."""
    
    CACHE_DIR = os.path.join(os.path.dirname(__file__), 'backtest_data')
    
    def __init__(self):
        os.makedirs(self.CACHE_DIR, exist_ok=True)
    
    def load(self, symbol: str, start_date: str, end_date: str) -> List[Candle]:
        """
        Cargar datos 4H.
        Usa caché local si existe, sino descarga de Binance.
        """
        cache_file = os.path.join(
            self.CACHE_DIR,
            f"{symbol}_4h_{start_date}_{end_date}.json"
        )
        
        if os.path.exists(cache_file):
            logger.info(f"  📁 Cargando caché: {symbol} (4H)")
            with open(cache_file, 'r') as f:
                raw = json.load(f)
            return [Candle(
                timestamp=k[0], open=float(k[1]), high=float(k[2]),
                low=float(k[3]), close=float(k[4]), volume=float(k[5])
            ) for k in raw]
        
        logger.info(f"  📥 Descargando {symbol} 4H ({start_date} → {end_date})...")
        klines = self._download(symbol, start_date, end_date)
        
        # Guardar caché
        with open(cache_file, 'w') as f:
            json.dump(klines, f)
        
        return [Candle(
            timestamp=k[0], open=float(k[1]), high=float(k[2]),
            low=float(k[3]), close=float(k[4]), volume=float(k[5])
        ) for k in klines]
    
    def _download(self, symbol: str, start_date: str, end_date: str) -> List:
        """Descargar klines 4H de Binance (sin autenticación)."""
        import urllib.request
        import urllib.parse
        
        all_klines = []
        start_ms = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp() * 1000)
        end_ms = int(datetime.strptime(end_date, '%Y-%m-%d').timestamp() * 1000)
        
        current = start_ms
        
        while current < end_ms:
            params = urllib.parse.urlencode({
                'symbol': symbol,
                'interval': '4h',
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
                
                # Progress
                pct = min(100, (current - start_ms) / (end_ms - start_ms) * 100)
                sys.stdout.write(f"\r    {symbol}: {pct:.0f}% ({len(all_klines)} velas 4H)")
                sys.stdout.flush()
                
                time.sleep(0.2)  # Rate limit
                
            except Exception as e:
                logger.warning(f"  ⚠️ Error descargando {symbol}: {e}")
                time.sleep(2)
                continue
        
        print()  # newline
        return all_klines


# ============================================================
# MRB STRATEGY (Mean Reversion Bands - Backtesting version)
# ============================================================

class MRBStrategy:
    """
    Estrategia Mean Reversion Bands - B2 Resilience.
    
    Señales:
      LONG:  Precio <= BB inferior + RSI < 35 + Vol > avg
      SHORT: Precio >= BB superior + RSI > 65 + Vol > avg
      
    Confirmación: EMA(50) como filtro macro.
    """
    
    def __init__(self, sl_atr_mult=1.5, tp_atr_mult=2.5):
        # Bollinger Bands
        self.bb_period = 20
        self.bb_std_dev = 2.0
        
        # Indicadores
        self.ema_trend = 50
        self.rsi_period = 14
        self.atr_period = 14
        self.volume_avg_period = 20
        
        # Umbrales
        self.rsi_oversold = 35
        self.rsi_overbought = 65
        self.min_strength = 0.60
        self.volume_threshold = 1.0
        
        # SL/TP
        self.sl_atr_mult = sl_atr_mult
        self.tp_atr_mult = tp_atr_mult
    
    def analyze(self, candles: List[Candle], symbol: str) -> Optional[Dict]:
        """Analizar velas 4H y generar señal de reversión."""
        if len(candles) < self.ema_trend + 5:
            return None
        
        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        volumes = [c.volume for c in candles]
        
        price = closes[-1]
        
        # Indicadores
        bb_upper, bb_middle, bb_lower = self._bollinger_bands(closes)
        rsi = self._rsi(closes, self.rsi_period)
        ema50 = self._ema(closes, self.ema_trend)
        atr = self._atr(highs, lows, closes, self.atr_period)
        vol_avg = sum(volumes[-self.volume_avg_period:]) / self.volume_avg_period
        vol_current = volumes[-1]
        
        # Distancia normalizada
        bb_width = bb_upper - bb_lower
        if bb_width == 0:
            return None
        
        dist_to_lower = (price - bb_lower) / bb_width
        dist_to_upper = (bb_upper - price) / bb_width
        
        # SL/TP
        sl_dist = atr * self.sl_atr_mult if atr > 0 else price * 0.015
        tp_dist = atr * self.tp_atr_mult if atr > 0 else price * 0.025
        
        # ========== LONG (Reversión desde sobreventa) ==========
        long_strength = 0.0
        long_reasons = []
        
        if price <= bb_lower * 1.005:
            long_strength += 0.35
            long_reasons.append("BB inferior")
        elif dist_to_lower < 0.15:
            long_strength += 0.20
            long_reasons.append("~BB inferior")
        
        if rsi < self.rsi_oversold:
            long_strength += 0.30
            long_reasons.append(f"RSI={rsi:.0f}")
        elif rsi < 40:
            long_strength += 0.15
            long_reasons.append(f"RSI={rsi:.0f}")
        
        if vol_current >= vol_avg * self.volume_threshold:
            long_strength += 0.15
            long_reasons.append("Vol")
        
        if price > ema50 * 0.97:
            long_strength += 0.20
            long_reasons.append(">EMA50")
        
        # ========== SHORT (Reversión desde sobrecompra) ==========
        short_strength = 0.0
        short_reasons = []
        
        if price >= bb_upper * 0.995:
            short_strength += 0.35
            short_reasons.append("BB superior")
        elif dist_to_upper < 0.15:
            short_strength += 0.20
            short_reasons.append("~BB superior")
        
        if rsi > self.rsi_overbought:
            short_strength += 0.30
            short_reasons.append(f"RSI={rsi:.0f}")
        elif rsi > 60:
            short_strength += 0.15
            short_reasons.append(f"RSI={rsi:.0f}")
        
        if vol_current >= vol_avg * self.volume_threshold:
            short_strength += 0.15
            short_reasons.append("Vol")
        
        if price < ema50 * 1.03:
            short_strength += 0.20
            short_reasons.append("<EMA50")
        
        # ========== GENERAR SEÑAL ==========
        long_ok = long_strength >= self.min_strength
        short_ok = short_strength >= self.min_strength
        
        if long_ok and (not short_ok or long_strength > short_strength):
            return {
                'side': Side.LONG,
                'strength': min(long_strength, 1.0),
                'entry': price,
                'sl': price - sl_dist,
                'tp': price + tp_dist,
                'reason': ' + '.join(long_reasons),
                'atr': atr
            }
        
        if short_ok:
            return {
                'side': Side.SHORT,
                'strength': min(short_strength, 1.0),
                'entry': price,
                'sl': price + sl_dist,
                'tp': price - tp_dist,
                'reason': ' + '.join(short_reasons),
                'atr': atr
            }
        
        return None
    
    # ===== Indicadores Técnicos =====
    
    def _bollinger_bands(self, data: List[float]) -> tuple:
        """Bollinger Bands (20, 2σ)."""
        if len(data) < self.bb_period:
            return data[-1], data[-1], data[-1]
        recent = data[-self.bb_period:]
        sma = sum(recent) / self.bb_period
        variance = sum((x - sma) ** 2 for x in recent) / self.bb_period
        std = math.sqrt(variance)
        return sma + (self.bb_std_dev * std), sma, sma - (self.bb_std_dev * std)
    
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
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
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
# BACKTESTING ENGINE (B2 - Conservador)
# ============================================================

class BacktestEngine:
    """
    Motor de backtesting B2 Resilience.
    Simula trading conservador: 3x leverage, 2% posición, 4H timeframe.
    """
    
    def __init__(
        self,
        initial_balance: float = 1000.0,
        position_size_pct: float = 2.0,
        max_open_positions: int = 3,
        leverage: int = 3,
        commission_pct: float = 0.04,
        sl_atr_mult: float = 1.5,
        tp_atr_mult: float = 2.5,
        cooldown_candles: int = 3,      # 3 velas = 12H de cooldown
        max_consecutive_losses: int = 2, # Pausa tras 2 pérdidas
        label: str = 'B2-MRB'
    ):
        self.initial_balance = initial_balance
        self.position_size_pct = position_size_pct
        self.max_open_positions = max_open_positions
        self.leverage = leverage
        self.commission_pct = commission_pct
        self.cooldown_candles = cooldown_candles
        self.max_consecutive_losses = max_consecutive_losses
        self.label = label
        
        self.strategy = MRBStrategy(sl_atr_mult, tp_atr_mult)
        self.loader = HistoricalDataLoader()
    
    def run(
        self,
        symbols: List[str],
        start_date: str = '2023-01-01',
        end_date: str = '2026-02-10'
    ) -> Dict[str, BacktestResult]:
        """Ejecutar backtest completo."""
        
        logger.info("=" * 70)
        logger.info(f"🛡️ BACKTESTING MRB STRATEGY [{self.label}]")
        logger.info(f"   Periodo: {start_date} → {end_date}")
        logger.info(f"   Pares: {', '.join(symbols)}")
        logger.info(f"   Balance: ${self.initial_balance:,.0f} │ Pos: {self.position_size_pct}%")
        logger.info(f"   SL: {self.strategy.sl_atr_mult}x ATR │ TP: {self.strategy.tp_atr_mult}x ATR")
        logger.info(f"   Leverage: {self.leverage}x │ Fee: {self.commission_pct}%")
        logger.info(f"   Min Strength: {self.strategy.min_strength} │ Cooldown: {self.cooldown_candles} velas (4H)")
        logger.info(f"   RSI Oversold: <{self.strategy.rsi_oversold} │ Overbought: >{self.strategy.rsi_overbought}")
        logger.info(f"   BB: ({self.strategy.bb_period}, {self.strategy.bb_std_dev}σ)")
        logger.info(f"   Max pérdidas consecutivas: {self.max_consecutive_losses}")
        logger.info("=" * 70)
        
        # 1. Descargar datos 4H
        logger.info("\n📥 Descargando datos históricos (4H)...")
        all_data = {}
        for sym in symbols:
            candles = self.loader.load(sym, start_date, end_date)
            if candles:
                all_data[sym] = candles
                logger.info(f"  ✅ {sym}: {len(candles)} velas (4H)")
        
        # 2. Backtest individual por símbolo
        logger.info("\n🔄 Ejecutando simulación B2...")
        results = {}
        
        for sym, candles in all_data.items():
            result = self._backtest_symbol(sym, candles)
            results[sym] = result
            self._print_symbol_result(result)
        
        # 3. Portfolio combinado
        logger.info("\n" + "=" * 70)
        self._print_portfolio_summary(results)
        
        # 4. Guardar resultados
        self._save_report(results, start_date, end_date)
        
        return results
    
    def _backtest_symbol(self, symbol: str, candles: List[Candle]) -> BacktestResult:
        """Backtest para un símbolo con reglas conservadoras de B2."""
        balance = self.initial_balance
        peak_balance = balance
        max_drawdown = 0
        
        trades = []
        open_trade = None
        lookback = 55
        cooldown_remaining = 0
        consecutive_losses = 0
        
        equity_curve = []
        
        for i in range(lookback, len(candles)):
            window = candles[i - lookback:i + 1]
            current_candle = candles[i]
            
            # Si hay trade abierto, verificar SL/TP
            if open_trade:
                hit = self._check_sl_tp(open_trade, current_candle)
                if hit:
                    exit_price, exit_reason = hit
                    trade = self._close_trade(
                        open_trade, exit_price, exit_reason,
                        current_candle.dt, balance
                    )
                    trades.append(trade)
                    balance += trade.pnl_usd
                    
                    # Track consecutive losses
                    if trade.pnl_usd < 0:
                        consecutive_losses += 1
                    else:
                        consecutive_losses = 0
                    
                    peak_balance = max(peak_balance, balance)
                    dd = (peak_balance - balance) / peak_balance * 100 if peak_balance > 0 else 0
                    max_drawdown = max(max_drawdown, dd)
                    
                    open_trade = None
                    cooldown_remaining = self.cooldown_candles
            
            # Cooldown entre trades
            if cooldown_remaining > 0:
                cooldown_remaining -= 1
            
            # Pausa por pérdidas consecutivas (regla B2)
            if consecutive_losses >= self.max_consecutive_losses:
                cooldown_remaining = max(cooldown_remaining, 6)  # Pausa 24H (6 velas 4H)
                consecutive_losses = 0  # Reset
            
            # Si no hay trade y cooldown terminó, buscar señal
            if not open_trade and cooldown_remaining <= 0:
                if balance <= 0:
                    break
                
                signal = self.strategy.analyze(window, symbol)
                
                if signal:
                    margin = balance * (self.position_size_pct / 100)
                    notional = margin * self.leverage
                    quantity = notional / signal['entry']
                    
                    open_trade = {
                        'symbol': symbol,
                        'side': signal['side'],
                        'entry_price': signal['entry'],
                        'sl': signal['sl'],
                        'tp': signal['tp'],
                        'quantity': quantity,
                        'entry_time': current_candle.dt,
                        'strength': signal['strength'],
                        'reason': signal['reason']
                    }
            
            equity_curve.append(balance)
        
        # Cerrar trade abierto al final
        if open_trade:
            final_price = candles[-1].close
            trade = self._close_trade(
                open_trade, final_price, 'END',
                candles[-1].dt, balance
            )
            trades.append(trade)
            balance += trade.pnl_usd
        
        return self._compute_metrics(symbol, trades, balance, max_drawdown, equity_curve)
    
    def _check_sl_tp(self, trade: Dict, candle: Candle) -> Optional[Tuple[float, str]]:
        """Verificar si SL o TP fueron alcanzados."""
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
        """Cerrar un trade y calcular PnL."""
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
        """Calcular métricas del backtest."""
        result = BacktestResult(symbol=symbol, period='2023-2026', trades=trades)
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
        
        # Rachas
        current_wins = 0
        current_losses = 0
        for t in trades:
            if t.pnl_usd > 0:
                current_wins += 1
                current_losses = 0
                result.max_consecutive_wins = max(result.max_consecutive_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                result.max_consecutive_losses = max(result.max_consecutive_losses, current_losses)
        
        # Sharpe Ratio (anualizado)
        if len(trades) > 1:
            returns = [t.pnl_pct for t in trades]
            avg_ret = sum(returns) / len(returns)
            std_ret = math.sqrt(sum((r - avg_ret)**2 for r in returns) / (len(returns) - 1))
            if std_ret > 0:
                trades_per_year = 365 * 6 / (result.avg_trade_duration_h or 24)  # 6 velas/día (4H)
                result.sharpe_ratio = (avg_ret / std_ret) * math.sqrt(min(trades_per_year, 365))
        
        return result
    
    def _print_symbol_result(self, r: BacktestResult):
        """Imprimir resultados de un símbolo."""
        emoji = '✅' if r.total_pnl_usd > 0 else '❌'
        
        logger.info(
            f"\n  {emoji} {r.symbol:10s} │ "
            f"Trades={r.total_trades:4d} │ "
            f"Win={r.win_rate:5.1f}% │ "
            f"PnL=${r.total_pnl_usd:>+10,.2f} ({r.total_pnl_pct:>+6.1f}%) │ "
            f"PF={r.profit_factor:.2f} │ "
            f"MaxDD={r.max_drawdown_pct:.1f}% │ "
            f"Sharpe={r.sharpe_ratio:.2f}"
        )
    
    def _print_portfolio_summary(self, results: Dict[str, BacktestResult]):
        """Resumen del portfolio completo."""
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
        
        logger.info("🛡️ RESUMEN PORTFOLIO B2 RESILIENCE (CONSERVADOR)")
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
        if total_trades > total_wins:
            logger.info(f"  💸 Avg Loss:           ${-total_loss_usd / (total_trades - total_wins):>+10,.2f}")
        logger.info("=" * 70)
        
        # Ranking por símbolo
        logger.info("\n🏆 RANKING POR SÍMBOLO:")
        sorted_results = sorted(results.values(), key=lambda x: x.total_pnl_usd, reverse=True)
        for i, r in enumerate(sorted_results, 1):
            emoji = '🥇🥈🥉'[i-1] if i <= 3 else f'#{i}'
            bar_len = max(0, int(r.total_pnl_pct / 5)) if r.total_pnl_pct > 0 else 0
            bar = '█' * min(bar_len, 30)
            logger.info(
                f"  {emoji} {r.symbol:10s} │ "
                f"PnL=${r.total_pnl_usd:>+10,.2f} │ "
                f"Win={r.win_rate:5.1f}% │ "
                f"PF={r.profit_factor:.2f} │ {bar}"
            )
        
        # PnL Mensual
        logger.info("\n📅 PnL MENSUAL:")
        monthly_pnl = {}
        for t in sorted(all_trades, key=lambda x: x.entry_time):
            month_key = t.entry_time.strftime('%Y-%m')
            monthly_pnl[month_key] = monthly_pnl.get(month_key, 0) + t.pnl_usd
        
        for month, pnl in sorted(monthly_pnl.items()):
            bar_len = int(abs(pnl) / 10)
            if pnl >= 0:
                bar = '🟢' * min(bar_len, 20)
            else:
                bar = '🔴' * min(bar_len, 20)
            logger.info(f"  {month} │ ${pnl:>+10,.2f} │ {bar}")
    
    def _save_report(self, results: Dict[str, BacktestResult],
                     start_date: str, end_date: str):
        """Guardar resultados en JSON."""
        report = {
            'engine': 'B2_RESILIENCE',
            'strategy': 'MRB (Mean Reversion Bands)',
            'timestamp': datetime.now().isoformat(),
            'period': f'{start_date} to {end_date}',
            'initial_balance': self.initial_balance,
            'settings': {
                'position_size_pct': self.position_size_pct,
                'leverage': self.leverage,
                'commission_pct': self.commission_pct,
                'sl_atr_mult': self.strategy.sl_atr_mult,
                'tp_atr_mult': self.strategy.tp_atr_mult,
                'bb_period': self.strategy.bb_period,
                'bb_std_dev': self.strategy.bb_std_dev,
                'rsi_oversold': self.strategy.rsi_oversold,
                'rsi_overbought': self.strategy.rsi_overbought,
                'cooldown_candles': self.cooldown_candles,
                'max_consecutive_losses': self.max_consecutive_losses
            },
            'results': {}
        }
        
        for sym, r in results.items():
            report['results'][sym] = {
                'total_trades': r.total_trades,
                'win_rate': round(r.win_rate, 2),
                'total_pnl_usd': round(r.total_pnl_usd, 2),
                'total_pnl_pct': round(r.total_pnl_pct, 2),
                'profit_factor': round(r.profit_factor, 2),
                'max_drawdown_pct': round(r.max_drawdown_pct, 2),
                'sharpe_ratio': round(r.sharpe_ratio, 2),
                'avg_trade_duration_h': round(r.avg_trade_duration_h, 1),
                'max_consecutive_wins': r.max_consecutive_wins,
                'max_consecutive_losses': r.max_consecutive_losses
            }
        
        report_path = os.path.join(
            os.path.dirname(__file__),
            f'backtest_b2_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        )
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"\n📁 Reporte B2 guardado: {report_path}")


# ============================================================
# MAIN — B2 RESILIENCE BACKTEST
# ============================================================

if __name__ == '__main__':
    START = '2023-01-01'
    END = '2026-02-10'
    
    SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']
    INITIAL = 1000.0
    
    def portfolio_stats(results, initial):
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
        return total_trades, wr, total_pnl, pf, dd, final, roi
    
    # ========== OPTIMIZATION: probar varias configuraciones ==========
    configs = [
        {
            'label': 'V1-Base',
            'rsi_os': 35, 'rsi_ob': 65, 'min_str': 0.60,
            'bb_std': 2.0, 'sl': 1.5, 'tp': 2.5, 'cooldown': 3
        },
        {
            'label': 'V2-StrictRSI',
            'rsi_os': 30, 'rsi_ob': 70, 'min_str': 0.60,
            'bb_std': 2.0, 'sl': 1.5, 'tp': 2.5, 'cooldown': 3
        },
        {
            'label': 'V3-HighStrength',
            'rsi_os': 30, 'rsi_ob': 70, 'min_str': 0.70,
            'bb_std': 2.0, 'sl': 1.5, 'tp': 3.0, 'cooldown': 4
        },
        {
            'label': 'V4-WiderBB',
            'rsi_os': 30, 'rsi_ob': 70, 'min_str': 0.70,
            'bb_std': 2.5, 'sl': 1.5, 'tp': 3.0, 'cooldown': 4
        },
        {
            'label': 'V5-Aggressive',
            'rsi_os': 30, 'rsi_ob': 70, 'min_str': 0.75,
            'bb_std': 2.5, 'sl': 2.0, 'tp': 4.0, 'cooldown': 6
        },
    ]
    
    all_results = []
    
    for cfg in configs:
        logger.info("\n" + "🛡️" * 35)
        logger.info(f"   B2 RESILIENCE — {cfg['label']}")
        logger.info("🛡️" * 35)
        
        engine = BacktestEngine(
            initial_balance=INITIAL,
            position_size_pct=2.0,
            leverage=3,
            commission_pct=0.04,
            sl_atr_mult=cfg['sl'],
            tp_atr_mult=cfg['tp'],
            cooldown_candles=cfg['cooldown'],
            max_consecutive_losses=2,
            label=cfg['label']
        )
        # Override strategy thresholds
        engine.strategy.rsi_oversold = cfg['rsi_os']
        engine.strategy.rsi_overbought = cfg['rsi_ob']
        engine.strategy.min_strength = cfg['min_str']
        engine.strategy.bb_std_dev = cfg['bb_std']
        
        results = engine.run(symbols=SYMBOLS, start_date=START, end_date=END)
        stats = portfolio_stats(results, INITIAL)
        all_results.append((cfg['label'], stats, results))
    
    # ========== TABLA COMPARATIVA ==========
    logger.info("\n" + "=" * 100)
    logger.info("⚔️  COMPARATIVA DE CONFIGURACIONES B2 RESILIENCE")
    logger.info("=" * 100)
    
    logger.info(f"\n  {'Config':<18s} {'Trades':>7s} {'WR':>6s} {'PnL':>13s} {'PF':>5s} {'MaxDD':>7s} {'Final $':>12s} {'ROI':>8s}")
    logger.info(f"  {'━'*82}")
    
    for name, (t, wr, pnl, pf, dd, final, roi), _ in all_results:
        marker = ' ✅' if roi > 0 else ''
        logger.info(
            f"  ➡️ {name:<16s} {t:>6,d} {wr:>5.1f}% ${pnl:>+11,.2f} {pf:>4.2f} {dd:>6.1f}% ${final:>10,.2f} {roi:>+7.1f}%{marker}"
        )
    
    # Mejor config
    best = max(all_results, key=lambda x: x[1][2])  # Máximo PnL
    logger.info(f"\n  🏆 MEJOR CONFIGURACIÓN: {best[0]} (ROI: {best[1][6]:+.1f}%)")
    
    logger.info("\n📊 DESGLOSE POR ACTIVO (Mejor config):")
    for symbol, res in best[2].items():
        logger.info(
            f"   {symbol:<10} │ PnL: ${res.total_pnl_usd:>8.2f} │ "
            f"WR: {res.win_rate:>5.1f}% │ PF: {res.profit_factor:>4.2f} │ "
            f"Trades: {res.total_trades} │ MaxDD: {res.max_drawdown_pct:.1f}%"
        )
    logger.info("=" * 100)
