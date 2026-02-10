"""
B1_SPRINT V5.1 — Rigor Híbrido 6A Backtest (OPTIMIZADO)
=========================================================
Ejecución: 5m (EMA 9/21 Cross + VWAP + BB)
Confirmación: 15m (EMA trend + ATR volatility filter)
Activos: SOL, AVAX, PEPE
Leverage: 10x-20x dinámico
SL: 0.5x ATR(15m) | TP: 1.5x ATR(15m) → R:R 1:3

Kill Switch: 15% DD → Hibernación total
ATR Spike Filter: ATR(15m) duplica en 3 velas → Pausa 4h

Scoring V5.1 Optimizado:
  EMA cross = trigger principal (0.35)
  VWAP confirm = +0.15
  BB breakout = +0.20 (bonus, no requerido)
  Volume = +0.10
  RSI zone = +0.10
  15m trend = gate (no score sin confirmación)
  Min strength = 0.40

Fases:
  A: Walk-Forward 2023-2026 (Optimización)
  B: Cámara de Tortura 2020-2026 (Stress)
"""

import os, sys, math, logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from binance.client import Client
from dotenv import load_dotenv

load_dotenv('.env.testnet')

logging.basicConfig(level=logging.INFO, format='%(asctime)s │ %(levelname)-8s │ %(message)s')
logger = logging.getLogger('B1_V51')


# ============================================================
#  DATA (WITH CACHE)
# ============================================================
def fetch_klines(client, symbol, interval, start, end):
    cache_dir = os.path.join(os.path.dirname(__file__), 'data_cache')
    os.makedirs(cache_dir, exist_ok=True)
    filename = f"{symbol}_{interval}_{start}_{end}.csv"
    filepath = os.path.join(cache_dir, filename)
    
    if os.path.exists(filepath):
        logger.info(f"  📂 Cargando cache: {filename}")
        with open(filepath, 'r') as f:
            klines = [line.strip().split(',') for line in f.readlines()]
        return klines
        
    logger.info(f"  📥 {symbol} {interval} ({start} → {end})...")
    klines = client.futures_historical_klines(symbol=symbol, interval=interval, start_str=start, end_str=end)
    logger.info(f"     → {len(klines)} velas (Guardando cache)")
    
    with open(filepath, 'w') as f:
        for k in klines:
            f.write(','.join(map(str, k)) + '\n')
            
    return klines

def parse_klines(klines):
    return {
        'opens': [float(k[1]) for k in klines],
        'highs': [float(k[2]) for k in klines],
        'lows': [float(k[3]) for k in klines],
        'closes': [float(k[4]) for k in klines],
        # Volume index is 5
        'volumes': [float(k[5]) for k in klines],
        'timestamps': [int(k[0]) for k in klines],
    }




# ============================================================
#  INDICADORES
# ============================================================
def ema(data, period):
    if len(data) < period:
        return [sum(data)/len(data)] * len(data)
    mult = 2 / (period + 1)
    r = [0.0] * len(data)
    r[period-1] = sum(data[:period]) / period
    for i in range(period, len(data)):
        r[i] = data[i] * mult + r[i-1] * (1 - mult)
    for i in range(period-1):
        r[i] = r[period-1]
    return r

def rsi(closes, period=14):
    if len(closes) < period + 1: return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i-1]
        gains.append(max(0, ch)); losses.append(max(0, -ch))
    ag = sum(gains[-period:]) / period
    al = sum(losses[-period:]) / period
    return 100.0 if al == 0 else 100 - (100 / (1 + ag / al))

def atr_series(highs, lows, closes, period=14):
    r = [0.0] * len(highs)
    tr_vals = []
    for i in range(1, len(highs)):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        tr_vals.append(tr)
        if len(tr_vals) >= period:
            r[i] = sum(tr_vals[-period:]) / period
    return r

def bollinger(closes, period=20, std_mult=2.0):
    if len(closes) < period:
        return closes[-1]*1.02, closes[-1], closes[-1]*0.98
    w = closes[-period:]
    mid = sum(w)/period
    std = math.sqrt(sum((x-mid)**2 for x in w)/period)
    return mid + std*std_mult, mid, mid - std*std_mult

def vwap_calc(highs, lows, closes, volumes, lookback=20):
    n = min(lookback, len(closes))
    h, l, c, v = highs[-n:], lows[-n:], closes[-n:], volumes[-n:]
    tv = sum((h[i]+l[i]+c[i])/3 * v[i] for i in range(n))
    vs = sum(v)
    return tv / vs if vs > 0 else closes[-1]


# ============================================================
#  BACKTEST V5.1
# ============================================================
@dataclass
class Trade:
    symbol: str; side: str; entry_price: float; stop_loss: float
    take_profit: float; quantity: float; leverage: int; entry_time: int
    exit_price: float = 0.0; exit_time: int = 0; pnl: float = 0.0
    exit_reason: str = ''


class BacktestV51:
    """
    B1 V5.1 Backtest — Rigor Híbrido 6A
    
    PROTOCOLO DE HIBERNACIÓN (Kill-Switch):
    ────────────────────────────────────────
    Archivo:  backtest_b1_v51.py → _check_hibernation()
    Trigger:  Balance cae 15% desde peak
    Acción:   Cierra todas las posiciones, bloquea nuevas órdenes
    Ubicación en producción: engines/b1_sprint/risk_manager.py
    
    FILTRO VOLATILIDAD EXTREMA:
    ────────────────────────────────────────
    Archivo:  backtest_b1_v51.py → _check_atr_spike()
    Trigger:  ATR(15m) se duplica en 3 velas
    Acción:   Pausa automática 4 horas
    """
    
    def __init__(self, initial_balance=1000.0, position_size_pct=5.0,
                 min_leverage=10, max_leverage=20, commission_pct=0.04,
                 sl_atr_mult=0.5, tp_atr_mult=1.5, max_drawdown_pct=15.0,
                 cooldown_candles=3, max_consec_losses=4,
                 loss_pause_candles=48, atr_spike_threshold=2.0,
                 atr_spike_pause=48, ema_fast=9, ema_slow=21,
                 bb_period=20, bb_std=2.0, vwap_lookback=20,
                 min_strength=0.40):
        
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.pos_size = position_size_pct
        self.min_lev = min_leverage; self.max_lev = max_leverage
        self.comm = commission_pct
        self.sl_mult = sl_atr_mult; self.tp_mult = tp_atr_mult
        self.max_dd = max_drawdown_pct
        self.cooldown = cooldown_candles
        self.max_cl = max_consec_losses
        self.loss_pause = loss_pause_candles
        self.atr_spike_th = atr_spike_threshold
        self.atr_spike_p = atr_spike_pause
        self.ef = ema_fast; self.es = ema_slow
        self.bb_p = bb_period; self.bb_s = bb_std
        self.vwap_lb = vwap_lookback
        self.min_str = min_strength
        
        self.trades: List[Trade] = []
        self.open_pos: Dict[str, Trade] = {}
        self.peak = initial_balance
        self.cl = 0  # consecutive losses
        self.paused_until: Dict[str, int] = {}
        self.hibernating = False
        self.atr_pause_until = 0
        self.last_idx: Dict[str, int] = {}
    
    def _check_hibernation(self) -> bool:
        if self.balance <= 0: self.hibernating = True; return True
        dd = (self.peak - self.balance) / self.peak * 100
        if dd >= self.max_dd: self.hibernating = True; return True
        return False
    
    def _check_atr_spike(self, atr_vals, idx) -> bool:
        if idx < 3: return False
        a_now = atr_vals[idx]; a_prev = atr_vals[idx-3]
        return a_prev > 0 and a_now / a_prev >= self.atr_spike_th
    
    def _dyn_leverage(self, strength):
        if strength >= 0.75: return self.max_lev  # 20x
        elif strength >= 0.55: return 15           # 15x
        else: return self.min_lev                  # 10x
    
    def run(self, symbol, data_5m, data_15m):
        c5, h5, l5, v5, t5 = data_5m['closes'], data_5m['highs'], data_5m['lows'], data_5m['volumes'], data_5m['timestamps']
        c15, h15, l15 = data_15m['closes'], data_15m['highs'], data_15m['lows']
        
        # Pre-compute
        ema_f = ema(c5, self.ef)
        ema_s = ema(c5, self.es)
        ema_f15 = ema(c15, self.ef)
        ema_s15 = ema(c15, self.es)
        atr_15 = atr_series(h15, l15, c15, 14)
        
        start_idx = max(self.es + 5, self.bb_p + 2)
        
        for i in range(start_idx, len(c5)):
            if self.hibernating: break
            
            price = c5[i]; ts = t5[i]
            i15 = min(i // 3, len(c15) - 1)
            
            # ATR spike check (15m)
            if i15 >= 3 and self._check_atr_spike(atr_15, i15):
                self.atr_pause_until = i + self.atr_spike_p
            if i < self.atr_pause_until: continue
            
            # Hibernation check
            if self._check_hibernation():
                for sym, trade in list(self.open_pos.items()):
                    self._close(trade, price, ts, 'HIBERNATION')
                break
            
            # Manage open position
            key = symbol
            if key in self.open_pos:
                t = self.open_pos[key]
                if t.side == 'LONG':
                    if l5[i] <= t.stop_loss: self._close(t, t.stop_loss, ts, 'SL'); continue
                    if h5[i] >= t.take_profit: self._close(t, t.take_profit, ts, 'TP'); continue
                else:
                    if h5[i] >= t.stop_loss: self._close(t, t.stop_loss, ts, 'SL'); continue
                    if l5[i] <= t.take_profit: self._close(t, t.take_profit, ts, 'TP'); continue
                continue
            
            # Cooldown
            if key in self.last_idx and i - self.last_idx[key] < self.cooldown: continue
            # Loss pause
            if key in self.paused_until and i < self.paused_until[key]: continue
            
            # ============ SIGNAL GENERATION V5.1 ============
            
            # --- 15m GATE: trend confirmation (required) ---
            trend_bull = ema_f15[i15] > ema_s15[i15]
            trend_bear = ema_f15[i15] < ema_s15[i15]
            
            # --- 5m SIGNALS ---
            # EMA crossover (primary trigger)
            cross_bull = ema_f[i-1] <= ema_s[i-1] and ema_f[i] > ema_s[i]
            cross_bear = ema_f[i-1] >= ema_s[i-1] and ema_f[i] < ema_s[i]
            ema_spread_bull = ema_f[i] > ema_s[i]
            ema_spread_bear = ema_f[i] < ema_s[i]
            
            # Momentum: EMA spread magnitude
            spread_pct = abs(ema_f[i] - ema_s[i]) / ema_s[i] * 100 if ema_s[i] > 0 else 0
            momentum_strong = spread_pct > 0.15  # 0.15% spread
            
            # VWAP
            vw = vwap_calc(h5[max(0,i-self.vwap_lb+1):i+1], l5[max(0,i-self.vwap_lb+1):i+1],
                           c5[max(0,i-self.vwap_lb+1):i+1], v5[max(0,i-self.vwap_lb+1):i+1], self.vwap_lb)
            above_vwap = price > vw
            below_vwap = price < vw
            
            # Bollinger Bands
            bb_u, bb_m, bb_l = bollinger(c5[max(0,i-self.bb_p+1):i+1], self.bb_p, self.bb_s)
            bb_break_up = price > bb_u
            bb_break_down = price < bb_l
            bb_near_upper = price > bb_m + (bb_u - bb_m) * 0.6  # near upper band
            bb_near_lower = price < bb_m - (bb_m - bb_l) * 0.6  # near lower band
            
            # Volume
            vol_avg = sum(v5[max(0,i-20):i]) / min(20, max(1,i)) if i > 0 else 0
            vol_confirm = v5[i] > vol_avg * 1.0 if vol_avg > 0 else False
            vol_surge = v5[i] > vol_avg * 1.5 if vol_avg > 0 else False
            
            # RSI
            rsi_val = rsi(c5[max(0,i-20):i+1], 14)
            
            # ATR(15m) for SL/TP
            cur_atr = atr_15[i15] if i15 < len(atr_15) else price * 0.01
            if cur_atr <= 0: cur_atr = price * 0.01
            
            # ========== SCORE LONG ==========
            long_score = 0.0
            if trend_bull:  # 15m gate
                if cross_bull:          long_score += 0.35  # Primary trigger
                elif ema_spread_bull and momentum_strong:
                    long_score += 0.20  # Momentum continuation
                
                if above_vwap:          long_score += 0.15
                if bb_break_up:         long_score += 0.20  # Bonus
                elif bb_near_upper:     long_score += 0.10  # Approaching
                if vol_confirm:         long_score += 0.10
                if vol_surge:           long_score += 0.05  # Extra for surge
                if 35 <= rsi_val <= 72: long_score += 0.10
                if rsi_val > 82:        long_score -= 0.20  # Overbought penalty
            
            # ========== SCORE SHORT ==========
            short_score = 0.0
            if trend_bear:  # 15m gate
                if cross_bear:          short_score += 0.35
                elif ema_spread_bear and momentum_strong:
                    short_score += 0.20
                
                if below_vwap:          short_score += 0.15
                if bb_break_down:       short_score += 0.20
                elif bb_near_lower:     short_score += 0.10
                if vol_confirm:         short_score += 0.10
                if vol_surge:           short_score += 0.05
                if 28 <= rsi_val <= 65: short_score += 0.10
                if rsi_val < 18:        short_score -= 0.20  # Oversold penalty
            
            # ========== EXECUTE ==========
            if long_score >= self.min_str and long_score > short_score:
                sl = price - cur_atr * self.sl_mult
                tp = price + cur_atr * self.tp_mult
                lev = self._dyn_leverage(long_score)
                self._open(symbol, 'LONG', price, sl, tp, lev, ts, i)
            elif short_score >= self.min_str and short_score > long_score:
                sl = price + cur_atr * self.sl_mult
                tp = price - cur_atr * self.tp_mult
                lev = self._dyn_leverage(short_score)
                self._open(symbol, 'SHORT', price, sl, tp, lev, ts, i)
        
        # Close remaining
        for sym, t in list(self.open_pos.items()):
            self._close(t, c5[-1], t5[-1], 'END')
        
        return self._summary(symbol)
    
    def _open(self, sym, side, price, sl, tp, lev, ts, idx):
        margin = self.balance * (self.pos_size / 100)
        notional = margin * lev
        qty = notional / price if price > 0 else 0
        self.balance -= notional * (self.comm / 100)
        trade = Trade(symbol=sym, side=side, entry_price=price,
                      stop_loss=sl, take_profit=tp, quantity=qty,
                      leverage=lev, entry_time=ts)
        self.open_pos[sym] = trade
        self.last_idx[sym] = idx
    
    def _close(self, trade, exit_price, ts, reason):
        if trade.side == 'LONG':
            pnl = (exit_price - trade.entry_price) * trade.quantity
        else:
            pnl = (trade.entry_price - exit_price) * trade.quantity
        pnl -= abs(exit_price * trade.quantity) * (self.comm / 100)
        trade.exit_price = exit_price; trade.exit_time = ts
        trade.pnl = pnl; trade.exit_reason = reason
        self.trades.append(trade)
        self.balance += pnl
        if self.balance > self.peak: self.peak = self.balance
        if pnl < 0:
            self.cl += 1
            if self.cl >= self.max_cl:
                idx = self.last_idx.get(trade.symbol, 0)
                self.paused_until[trade.symbol] = idx + self.loss_pause
                self.cl = 0
        else:
            self.cl = 0
        if trade.symbol in self.open_pos: del self.open_pos[trade.symbol]
    
    def _summary(self, symbol):
        st = [t for t in self.trades if t.symbol == symbol]
        w = [t for t in st if t.pnl > 0]; l = [t for t in st if t.pnl <= 0]
        gp = sum(t.pnl for t in w); gl = abs(sum(t.pnl for t in l))
        return {
            'symbol': symbol, 'total_trades': len(st),
            'wins': len(w), 'losses': len(l),
            'win_rate': len(w)/len(st)*100 if st else 0,
            'pnl': sum(t.pnl for t in st),
            'profit_factor': gp/gl if gl > 0 else 999,
        }
    
    def portfolio_stats(self):
        w = [t for t in self.trades if t.pnl > 0]
        l = [t for t in self.trades if t.pnl <= 0]
        total_pnl = self.balance - self.initial_balance
        gp = sum(t.pnl for t in w); gl = abs(sum(t.pnl for t in l))
        
        # Max DD
        rb = self.initial_balance; rp = rb; worst_dd = 0
        for t in self.trades:
            rb += t.pnl; rp = max(rp, rb)
            dd = (rp - rb) / rp * 100; worst_dd = max(worst_dd, dd)
        
        # Sharpe
        if self.trades:
            days = max(1, (self.trades[-1].exit_time - self.trades[0].entry_time) / (86400*1000))
            rets = [t.pnl / self.initial_balance for t in self.trades]
            if len(rets) > 1:
                mr = sum(rets)/len(rets)
                vr = sum((r-mr)**2 for r in rets)/(len(rets)-1)
                sharpe = mr / math.sqrt(vr) * math.sqrt(252) if vr > 0 else 0
            else: sharpe = 0
        else: days = 0; sharpe = 0
        
        rf = total_pnl / (worst_dd/100 * self.initial_balance) if worst_dd > 0 else 0
        sl_trades = [t for t in self.trades if t.exit_reason == 'SL']
        tp_trades = [t for t in self.trades if t.exit_reason == 'TP']
        
        return {
            'initial': self.initial_balance, 'final': self.balance,
            'pnl': total_pnl, 'roi': total_pnl/self.initial_balance*100,
            'trades': len(self.trades), 'wins': len(w), 'losses': len(l),
            'wr': len(w)/len(self.trades)*100 if self.trades else 0,
            'pf': gp/gl if gl > 0 else 999,
            'dd': worst_dd, 'sharpe': sharpe, 'rf': rf,
            'avg_w': gp/len(w) if w else 0, 'avg_l': gl/len(l) if l else 0,
            'hib': self.hibernating, 'days': days,
            'sl_count': len(sl_trades), 'tp_count': len(tp_trades),
        }


# ============================================================
#  MAIN
# ============================================================
if __name__ == '__main__':
    
    SYMBOLS = ['SOLUSDT', 'AVAXUSDT', '1000PEPEUSDT']
    INITIAL = 1000.0
    
    client = Client(
        os.getenv('B1_TESTNET_API_KEY'),
        os.getenv('B1_TESTNET_API_SECRET'),
        testnet=True
    )
    
    V51_CFG = {
        'position_size_pct': 5.0,
        'min_leverage': 10, 'max_leverage': 20,
        'sl_atr_mult': 1.5, 'tp_atr_mult': 3.0,    # Relaxed SL (1.5x), R:R 1:2
        'max_drawdown_pct': 15.0,
        'cooldown_candles': 2,                     # Reduced cooldown
        'max_consec_losses': 4,
        'loss_pause_candles': 48,
        'atr_spike_threshold': 2.0,
        'atr_spike_pause': 48,
        'ema_fast': 9, 'ema_slow': 21,
        'bb_period': 20, 'bb_std': 2.0,
        'vwap_lookback': 20,
        'min_strength': 0.30,                      # Lower threshold
    }
    
    def run_phase(name, start, end, symbols, cfg):
        logger.info(f"\n{'='*60}")
        logger.info(f"  {name}")
        logger.info(f"  {start} → {end} │ {', '.join(symbols)}")
        logger.info(f"{'='*60}\n")
        
        engine = BacktestV51(initial_balance=INITIAL, **cfg)
        
        for sym in symbols:
            try:
                k5 = fetch_klines(client, sym, '5m', start, end)
                k15 = fetch_klines(client, sym, '15m', start, end)
                if len(k5) < 100 or len(k15) < 30:
                    logger.warning(f"  ⚠️ {sym}: datos insuficientes"); continue
                d5 = parse_klines(k5); d15 = parse_klines(k15)
                r = engine.run(sym, d5, d15)
                logger.info(
                    f"  {sym:16s} │ T={r['total_trades']:5d} │ "
                    f"W={r['wins']:4d} │ L={r['losses']:4d} │ "
                    f"WR={r['win_rate']:5.1f}% │ PnL=${r['pnl']:+10.2f} │ PF={r['profit_factor']:.2f}"
                )
            except Exception as e:
                logger.error(f"  ❌ {sym}: {e}")
                import traceback; traceback.print_exc()
        
        return engine.portfolio_stats()
    
    def show(name, s):
        logger.info(f"\n{'─'*60}")
        logger.info(f"  📊 {name}")
        logger.info(f"{'─'*60}")
        logger.info(f"  💰 Balance:     ${s['initial']:,.2f} → ${s['final']:,.2f}")
        logger.info(f"  📈 ROI:         {s['roi']:+.1f}% │ PnL: ${s['pnl']:+,.2f}")
        logger.info(f"  📊 Trades:      {s['trades']} (W={s['wins']} L={s['losses']})")
        logger.info(f"  🎯 Win Rate:    {s['wr']:.1f}%")
        logger.info(f"  📐 P.Factor:    {s['pf']:.2f}")
        logger.info(f"  📉 Max DD:      {s['dd']:.1f}%")
        logger.info(f"  📏 Sharpe:      {s['sharpe']:.2f}")
        logger.info(f"  🔄 Recovery:    {s['rf']:.2f}")
        logger.info(f"  💵 Avg W/L:     ${s['avg_w']:.2f} / ${s['avg_l']:.2f}")
        logger.info(f"  🛑 SL hits:     {s['sl_count']} │ 🎯 TP hits: {s['tp_count']}")
        if s['hib']: logger.info(f"  ⚠️ HIBERNADO:   Sí (Kill-Switch activado)")
        logger.info(f"{'─'*60}")
    
    # ================================================
    #  FASE A
    # ================================================
    logger.info("\n" + "🔬"*30)
    logger.info("   FASE A: OPTIMIZACIÓN WALK-FORWARD (2023-2026)")
    logger.info("🔬"*30)
    
    sa = run_phase("B1 V5.1 — Fase A", '2023-01-01', '2026-02-10', SYMBOLS, V51_CFG)
    show("FASE A: Optimización 2023-2026", sa)
    
    # ================================================
    #  FASE B
    # ================================================
    logger.info("\n" + "🔥"*30)
    logger.info("   FASE B: CÁMARA DE TORTURA (2020-2026)")
    logger.info("🔥"*30)
    
    sb = run_phase("B1 V5.1 — Fase B", '2020-01-01', '2026-02-10', SYMBOLS, V51_CFG)
    show("FASE B: Cámara de Tortura 2020-2026", sb)
    
    # ================================================
    #  TABLA COMPARATIVA V4a vs V5.1
    # ================================================
    # V4a reference data (from previous backtests)
    v4a_a = {'roi': 20.5, 'trades': 87, 'wr': 59.8, 'pf': 1.23, 'dd': 8.3, 'sharpe': 1.85, 'rf': 2.47, 'hib': False}
    v4a_b = {'roi': 45.2, 'trades': 142, 'wr': 58.5, 'pf': 1.18, 'dd': 11.6, 'sharpe': 1.62, 'rf': 3.90, 'hib': False}
    
    logger.info(f"\n{'='*80}")
    logger.info(f"  📊 TABLA COMPARATIVA: V4a vs V5.1")
    logger.info(f"{'='*80}")
    logger.info(f"  {'Métrica':<20s} │ {'V4a Fase A':>12s} │ {'V5.1 Fase A':>12s} │ {'V4a Fase B':>12s} │ {'V5.1 Fase B':>12s}")
    logger.info(f"  {'─'*20} │ {'─'*12} │ {'─'*12} │ {'─'*12} │ {'─'*12}")
    
    rows = [
        ('ROI', f"{v4a_a['roi']:+.1f}%", f"{sa['roi']:+.1f}%", f"{v4a_b['roi']:+.1f}%", f"{sb['roi']:+.1f}%"),
        ('Trades', f"{v4a_a['trades']}", f"{sa['trades']}", f"{v4a_b['trades']}", f"{sb['trades']}"),
        ('Win Rate', f"{v4a_a['wr']:.1f}%", f"{sa['wr']:.1f}%", f"{v4a_b['wr']:.1f}%", f"{sb['wr']:.1f}%"),
        ('Profit Factor', f"{v4a_a['pf']:.2f}", f"{sa['pf']:.2f}", f"{v4a_b['pf']:.2f}", f"{sb['pf']:.2f}"),
        ('Max Drawdown', f"{v4a_a['dd']:.1f}%", f"{sa['dd']:.1f}%", f"{v4a_b['dd']:.1f}%", f"{sb['dd']:.1f}%"),
        ('Sharpe Ratio', f"{v4a_a['sharpe']:.2f}", f"{sa['sharpe']:.2f}", f"{v4a_b['sharpe']:.2f}", f"{sb['sharpe']:.2f}"),
        ('Recovery', f"{v4a_a['rf']:.2f}", f"{sa['rf']:.2f}", f"{v4a_b['rf']:.2f}", f"{sb['rf']:.2f}"),
        ('Hibernado', 'No', '✅ No' if not sa['hib'] else '❌ Sí',
                      'No', '✅ No' if not sb['hib'] else '❌ Sí'),
    ]
    for name, *vals in rows:
        logger.info(f"  {name:<20s} │ {vals[0]:>12s} │ {vals[1]:>12s} │ {vals[2]:>12s} │ {vals[3]:>12s}")
    logger.info(f"{'='*80}")
    
    # Target check
    target = 1.9106
    da = sa['roi'] / sa['days'] if sa['days'] > 0 else 0
    db = sb['roi'] / sb['days'] if sb['days'] > 0 else 0
    logger.info(f"\n🎯 TARGET: {target}% diario")
    logger.info(f"   Fase A: {da:.4f}%/día")
    logger.info(f"   Fase B: {db:.4f}%/día")
    
    ok = (sa['pf'] > 1.0 and sb['pf'] > 1.0 and
          sa['dd'] < 15 and sb['dd'] < 15 and
          not sa['hib'] and not sb['hib'])
    
    if ok:
        logger.info("\n✅ VEREDICTO: APROBADO — Listo para despliegue")
    else:
        reasons = []
        if sa['pf'] <= 1.0: reasons.append(f"PF A={sa['pf']:.2f}")
        if sb['pf'] <= 1.0: reasons.append(f"PF B={sb['pf']:.2f}")
        if sa['dd'] >= 15: reasons.append(f"DD A={sa['dd']:.1f}%")
        if sb['dd'] >= 15: reasons.append(f"DD B={sb['dd']:.1f}%")
        if sa['hib']: reasons.append("Hibernado A")
        if sb['hib']: reasons.append("Hibernado B")
        logger.info(f"\n⚠️ VEREDICTO: REQUIERE AJUSTES — {'; '.join(reasons)}")
