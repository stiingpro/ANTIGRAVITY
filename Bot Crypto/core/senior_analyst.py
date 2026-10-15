"""
ANTIGRAVITY — Senior Multi-Asset & Monetary Debasement Analyst
==============================================================
Escáner cuantitativo e institucional en tiempo real para:
1. Macro & Liquidez (DXY, US10Y Yield, VIX, Petróleo como presión inflacionaria)
2. Termómetros de Degradación Monetaria (BTC/Oro, Oro/Plata, Cobre/Oro, S&P500/Oro)
3. Criptomonedas Principales (BTC, ETH, SOL, AVAX, LINK, DOT) + Derivados (Funding Rate & Open Interest)
4. Commodities (Oro GC=F / PAXG, Plata SI=F, Cobre HG=F, Petróleo CL=F, Uranio URA, Mineras GDX)
5. Acciones / Índices (S&P 500 SPY, Nasdaq 100 QQQ)

Uso directo:
    py -m core.senior_analyst
"""

import json
import math
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional


class SeniorMarketAnalyst:
    """
    Motor de Inteligencia de Mercado Multi-Activo (Opción A: Copiloto Institucional).
    """

    CRYPTO_ASSETS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'AVAXUSDT', 'LINKUSDT', 'DOTUSDT']

    MACRO_AND_TRADFI = {
        # Macro / Tasas / Volatilidad
        'DX-Y.NYB': {'name': 'Dólar Index (DXY)', 'category': 'MACRO'},
        '^TNX':     {'name': 'Bono EE.UU. 10Y (%)', 'category': 'MACRO'},
        '^VIX':     {'name': 'Volatilidad S&P (VIX)', 'category': 'MACRO'},
        # Commodities (con su ticker nativo en Binance Futures)
        'GC=F':     {'name': 'Oro (Binance: XAUUSDT / PAXGUSDT)', 'category': 'COMMODITY'},
        'SI=F':     {'name': 'Plata (Binance: XAGUSDT)', 'category': 'COMMODITY'},
        'HG=F':     {'name': 'Cobre (Binance: COPPERUSDT)', 'category': 'COMMODITY'},
        'CL=F':     {'name': 'Petróleo WTI (Binance: CLUSDT)', 'category': 'COMMODITY'},
        # Acciones y ETFs Estratégicos (con su ticker nativo en Binance Futures)
        'SPY':      {'name': 'S&P 500 (Binance: SPYUSDT)', 'category': 'EQUITY'},
        'QQQ':      {'name': 'Nasdaq 100 (Binance: QQQUSDT)', 'category': 'EQUITY'},
        'NVDA':     {'name': 'NVIDIA Corp (Binance: NVDAUSDT)', 'category': 'EQUITY'},
        'GDX':      {'name': 'Mineras de Oro (Binance: GDXUSDT)', 'category': 'EQUITY'},
        'URA':      {'name': 'Uranio & Nuclear (Binance: URNMUSDT)', 'category': 'EQUITY'},
    }

    @staticmethod
    def _fetch_json(url: str, timeout: int = 10) -> Any:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))

    @staticmethod
    def _calc_rsi_wilder(closes: List[float], period: int = 14) -> float:
        """RSI suavizado de Wilder (idéntico a TradingView)."""
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

    @staticmethod
    def _calc_ema(closes: List[float], period: int) -> float:
        if not closes:
            return 0.0
        if len(closes) < period:
            return sum(closes) / len(closes)
        k = 2.0 / (period + 1)
        ema = sum(closes[:period]) / period
        for val in closes[period:]:
            ema = val * k + ema * (1.0 - k)
        return ema

    def _scan_single_crypto(self, sym: str) -> Dict[str, Any]:
        try:
            t = self._fetch_json(f'https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={sym}')
            f = self._fetch_json(f'https://fapi.binance.com/fapi/v1/premiumIndex?symbol={sym}')
            oi = self._fetch_json(f'https://fapi.binance.com/fapi/v1/openInterest?symbol={sym}')
            kl = self._fetch_json(f'https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval=1d&limit=210')

            closes = [float(x[4]) for x in kl]
            highs = [float(x[2]) for x in kl]
            lows = [float(x[3]) for x in kl]

            price = float(t['lastPrice'])
            chg_24h = float(t['priceChangePercent'])
            funding_pct = float(f.get('lastFundingRate', 0.0)) * 100.0
            oi_usd = float(oi.get('openInterest', 0.0)) * price

            ema21 = self._calc_ema(closes, 21)
            sma50 = sum(closes[-50:]) / 50.0 if len(closes) >= 50 else price
            sma200 = sum(closes[-200:]) / 200.0 if len(closes) >= 200 else price
            rsi14 = self._calc_rsi_wilder(closes, 14)

            high_90d = max(highs[-90:]) if len(highs) >= 90 else max(highs)
            low_90d = min(lows[-90:]) if len(lows) >= 90 else min(lows)
            pos_in_90d = ((price - low_90d) / (high_90d - low_90d) * 100.0) if high_90d > low_90d else 50.0

            regime = "ALCISTA" if price > sma200 else "BAJISTA"
            if price > sma50 > sma200:
                regime = "ALCISTA FUERTE"
            elif price > sma200 and price < sma50:
                regime = "PULLBACK ALCISTA (ZONA VALOR)"

            signal_note = "Neutral"
            if price > sma200 and funding_pct < 0:
                signal_note = "💎 ABSORCIÓN / SHORT SQUEEZE (Tendencia Alcista + Funding Negativo)"
            elif price > sma200 and abs(price - sma50) / sma50 < 0.03 and 40 <= rsi14 <= 58:
                signal_note = "🚀 PULLBACK A SMA50 (Entrada Swing B2/B3)"
            elif rsi14 > 75 and funding_pct > 0.03:
                signal_note = "🚨 EUFORIA APALANCADA (Riesgo de Liquidación Long)"
            elif rsi14 < 32:
                signal_note = "💎 SOBREVENTA EXTREMA (Vigilar Spring)"

            return {
                'symbol': sym,
                'price': price,
                'chg_24h': chg_24h,
                'funding_pct': funding_pct,
                'oi_millions': oi_usd / 1e6,
                'ema21': ema21,
                'sma50': sma50,
                'sma200': sma200,
                'rsi14': rsi14,
                'pos_90d_pct': pos_in_90d,
                'regime': regime,
                'signal': signal_note,
            }
        except Exception as e:
            return {'symbol': sym, 'error': str(e)}

    def scan_crypto_derivatives(self) -> Dict[str, Dict[str, Any]]:
        """Escanea precios, estructura 1D, Funding Rate y Open Interest en Binance en paralelo."""
        from concurrent.futures import ThreadPoolExecutor
        results = {}
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = {sym: ex.submit(self._scan_single_crypto, sym) for sym in self.CRYPTO_ASSETS}
            for sym in self.CRYPTO_ASSETS:
                results[sym] = futures[sym].result()
        return results

    def _scan_single_tradfi(self, sym: str, meta: Dict[str, str]) -> Dict[str, Any]:
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?interval=1d&range=1y"
            data = self._fetch_json(url)
            res = data['chart']['result'][0]
            quote = res['indicators']['quote'][0]
            closes = [float(c) for c in quote['close'] if c is not None]

            price = closes[-1]
            prev = closes[-2] if len(closes) > 1 else price
            chg_1d = ((price - prev) / prev * 100.0) if prev else 0.0

            sma50 = sum(closes[-50:]) / 50.0 if len(closes) >= 50 else price
            sma200 = sum(closes[-200:]) / 200.0 if len(closes) >= 200 else price
            rsi14 = self._calc_rsi_wilder(closes, 14)

            high_52w = max(closes)
            low_52w = min(closes)
            pos_52w_pct = ((price - low_52w) / (high_52w - low_52w) * 100.0) if high_52w > low_52w else 50.0

            if price > sma50 > sma200:
                trend = "ALCISTA FUERTE"
            elif price > sma200:
                trend = "PULLBACK EN TENDENCIA"
            elif price < sma200 and rsi14 < 38:
                trend = "DESCUENTO PROFUNDO / ACUMULACIÓN"
            else:
                trend = "CORRECCIÓN / BAJISTA"

            return {
                'symbol': sym,
                'name': meta['name'],
                'category': meta['category'],
                'price': price,
                'chg_1d': chg_1d,
                'sma50': sma50,
                'sma200': sma200,
                'rsi14': rsi14,
                'high_52w': high_52w,
                'low_52w': low_52w,
                'pos_52w_pct': pos_52w_pct,
                'trend': trend,
            }
        except Exception as e:
            return {'symbol': sym, 'name': meta['name'], 'error': str(e)}

    def scan_macro_and_tradfi(self) -> Dict[str, Dict[str, Any]]:
        """Escanea Macro, Commodities y Acciones desde Yahoo Finance en paralelo."""
        from concurrent.futures import ThreadPoolExecutor
        results = {}
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures = {
                sym: ex.submit(self._scan_single_tradfi, sym, meta)
                for sym, meta in self.MACRO_AND_TRADFI.items()
            }
            for sym in self.MACRO_AND_TRADFI:
                results[sym] = futures[sym].result()
        return results

    def generate_executive_report(self) -> str:
        """Genera el informe completo del Analista Senior listo para consola o Telegram."""
        crypto = self.scan_crypto_derivatives()
        tradfi = self.scan_macro_and_tradfi()

        btc_p = crypto.get('BTCUSDT', {}).get('price', 0.0)
        gold_p = tradfi.get('GC=F', {}).get('price', 0.0)
        silv_p = tradfi.get('SI=F', {}).get('price', 0.0)
        copp_p = tradfi.get('HG=F', {}).get('price', 0.0)
        spy_p = tradfi.get('SPY', {}).get('price', 0.0)
        dxy_p = tradfi.get('DX-Y.NYB', {}).get('price', 0.0)
        tnx_p = tradfi.get('^TNX', {}).get('price', 0.0)
        vix_p = tradfi.get('^VIX', {}).get('price', 0.0)

        # Ratios de Degradación Monetaria
        btc_gold_ratio = (btc_p / gold_p) if gold_p > 0 else 0.0
        gold_silver_ratio = (gold_p / silv_p) if silv_p > 0 else 0.0
        copper_gold_ratio = (copp_p / gold_p * 1000.0) if gold_p > 0 else 0.0
        spy_gold_ratio = (spy_p / gold_p) if gold_p > 0 else 0.0

        now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        lines = [
            f"🏛️ *INFORME EJECUTIVO — ANALISTA SENIOR MULTI-ACTIVO*",
            f"⏰ Fecha: `{now_str}`\n",
            f"🌍 *1. RADAR MACRO & DEGRADACIÓN MONETARIA*",
            f"• *DXY (Dólar):* `{dxy_p:.2f}` | *US10Y Yield:* `{tnx_p:.2f}%` | *VIX:* `{vix_p:.2f}`",
            f"• *Ratio BTC / Oro:* `{btc_gold_ratio:.2f} oz` _(Poder adquisitivo real de BTC)_",
            f"• *Ratio Oro / Plata:* `{gold_silver_ratio:.1f}` _(>75 indica Plata subvaluada vs Oro)_",
            f"• *Ratio Cobre / Oro (x1000):* `{copper_gold_ratio:.2f}` _(Pulso industrial IA/Electrificación)_",
            f"• *Ratio S&P 500 / Oro:* `{spy_gold_ratio:.3f}`\n",
        ]

        # Diagnóstico de Riesgo Macro
        if tnx_p > 5.0 and dxy_p > 101.5:
            lines.append("⚠️ *Alerta Macro:* Tasas a 10 años (`>5.0%`) y DXY (`>101.5`) en zona de presión restrictiva. Evitar compras en techos; priorizar entradas en *pullbacks* o activos con *short squeeze*.\n")
        else:
            lines.append("🟢 *Clima Macro:* Liquidez benigna para activos duros y de riesgo.\n")

        lines.append("💎 *2. CRIPTOMONEDAS & MICROESTRUCTURA (FUTUROS)*")
        for sym, d in crypto.items():
            if 'error' in d:
                continue
            lines.append(
                f"• *{sym}*: `${d['price']:,.2f}` ({d['chg_24h']:+.1f}%) | RSI: `{d['rsi14']:.0f}` | "
                f"Funding: `{d['funding_pct']:+.4f}%` | OI: `${d['oi_millions']:,.0f}M`\n"
                f"  ↳ _{d['regime']}_ — {d['signal']}"
            )

        lines.append("\n🛢️ *3. COMMODITIES & ACCIONES ESTRATÉGICAS*")
        for sym, d in tradfi.items():
            if 'error' in d or d.get('category') == 'MACRO':
                continue
            lines.append(
                f"• *{d['name']} ({sym})*: `${d['price']:,.2f}` ({d['chg_1d']:+.1f}%) | "
                f"RSI: `{d['rsi14']:.0f}` | Rango 52s: `{d['pos_52w_pct']:.0f}%` → _{d['trend']}_"
            )

        return "\n".join(lines)


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    analyst = SeniorMarketAnalyst()
    print(analyst.generate_executive_report())

