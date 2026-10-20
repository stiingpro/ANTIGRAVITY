"""
DEMO EN VIVO BINANCE FUTURES — ARQUITECTURA TRIFECTA 2026 (B1, B2, B3 V8)
=========================================================================
Ejecuta los 3 Motores Campeones (reemplazados con las estrategias ganadoras
de la regresión Ene-Sep 2026) conectándose en tiempo real a los datos de
Binance Futures (https://fapi.binance.com) con una cuenta Demo persistente
de $3,000 USD ($1,000 USD por motor) y espejo opcional en Binance Testnet.

Motores activos (Cartera Propia V8.1 — 16 Activos):
  - B1 (B1_RANGE_GRID_V8 - 20% Capital = $600): Grid Dinámico & Reversión en Rango (ADX < 25)
    Activos: SOLUSDT, BNBUSDT, LINKUSDT
  - B2 (B2_REL_STRENGTH_V8 - 40% Capital = $1,200): Rotación por Fuerza Relativa (ROC 15d + ADX > 18)
    Activos: ETHUSDT, RENDERUSDT, UNIUSDT, TAOUSDT, HYPEUSDT, XAGUSDT, CLUSDT, NVDAUSDT
  - B3 (B3_ANTI_DEBASEMENT_V8 - 40% Capital = $1,200): Bóveda Anti-Degradación Wyckoff (RSI < 30.5 / Z < -1.80)
    Activos: BTCUSDT, PAXGUSDT, COPPERUSDT, SPYUSDT, QQQUSDT

Uso:
  py demo_trifecta_2026.py --once              # Escaneo en vivo único + reporte completo
  py demo_trifecta_2026.py --loop              # Dejar corriendo 24/7 (escaneo cada 5 min)
  py demo_trifecta_2026.py --status            # Ver estado actual del portafolio Demo
  py demo_trifecta_2026.py --reset             # Reiniciar cuenta Demo a $3,000 ($1,000 c/u)
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime
from typing import Dict, List, Optional
import urllib.request
import urllib.parse

from engines.b1_sprint.engine import B1SprintEngine
from engines.b1_sprint.strategy import B1Strategy
from engines.b2_resilience.engine import B2ResilienceEngine
from engines.b2_resilience.strategy import B2Strategy
from engines.b3_anchor.engine import B3AnchorEngine
from engines.b3_anchor.strategy import B3Strategy
from exchange_connector import ExchangeConnector
from dotenv import load_dotenv
import core.indicators as ind
import pandas as pd
import asyncio
import math

load_dotenv(".env.testnet")

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_portfolio_state.json")
BINANCE_FAPI_URL = "https://fapi.binance.com"
TAKER_FEE = 0.0004  # 0.04% comisión estándar Binance Futures USDT-M

# Precisión de cantidad para enviar órdenes reales al Testnet/Demo de Binance
TESTNET_QTY_PRECISION = {
    "SOLUSDT": 0, "BNBUSDT": 2, "LINKUSDT": 1,
    "ETHUSDT": 3, "AVAXUSDT": 1, "RENDERUSDT": 1, "UNIUSDT": 0,
    "TAOUSDT": 2, "HYPEUSDT": 2, "XAGUSDT": 1, "CLUSDT": 1, "NVDAUSDT": 2,
    "BTCUSDT": 3, "PAXGUSDT": 3, "XAUUSDT": 2, "COPPERUSDT": 1,
    "SPYUSDT": 2, "QQQUSDT": 2, "ONDOUSDT": 1
}


def sync_positions_to_binance_demo_api(state: Dict) -> List[str]:
    """
    Sincroniza las posiciones de B1, B2 y B3 directamente con las 3 API Keys
    de Binance Demo Trading (B1_TESTNET_SPRINT, B2_TESTNET_RESILIENCE, B3_TESTNET_ANCHOR)
    para que aparezcan en vivo en la interfaz web de Binance Demo Trading.
    """
    sync_logs = []
    connectors = {}
    for m in ("B1", "B2", "B3"):
        try:
            c = ExchangeConnector(motor=m, environment="testnet")
            if c.connect():
                connectors[m] = c
        except Exception as e:
            sync_logs.append(f"Aviso conexión API {m}: {e}")

    if not connectors:
        return sync_logs

    # Obtener posiciones actualmente abiertas en la cuenta Binance Demo Trading
    ref_conn = connectors.get("B3") or connectors.get("B2") or connectors.get("B1")
    try:
        exchange_positions = ref_conn.get_open_positions()
    except Exception:
        exchange_positions = []

    ex_map = {(p["symbol"], p["side"]): p for p in exchange_positions}

    # Cerrar posiciones residuales antiguas (ej. BTCUSDT SHORT x1 de pruebas viejas) que no estén en el estado V8
    desired_map = {}
    for m in ("B1", "B2", "B3"):
        for sym, pos in state["engines"][m]["open_positions"].items():
            desired_map[(sym, pos["side"])] = (m, pos)

    async def _run_sync():
        # Abrir en Binance Demo Trading las posiciones activas de B1, B2 y B3 que aún no estén en el exchange
        for (sym, side), (m, pos) in desired_map.items():
            if (sym, side) in ex_map or pos.get("binance_demo_order_id") or pos.get("binance_demo_note"):
                continue
            conn = connectors.get(m, ref_conn)
            prec = TESTNET_QTY_PRECISION.get(sym, 2)
            factor = 10 ** prec
            qty = math.floor(pos["quantity"] * factor) / factor
            if qty <= 0:
                continue
            order_side = "BUY" if side == "LONG" else "SELL"
            try:
                conn.change_leverage(sym, int(pos.get("leverage", 2)))
            except Exception:
                pass
            try:
                order = await conn.create_order(
                    symbol=sym, side=order_side, positionSide=side,
                    order_type="MARKET", quantity=qty
                )
                pos["binance_demo_order_id"] = order.get("orderId")
                sync_logs.append(
                    f"[API DEMO BINANCE - {m}_TESTNET] Ejecutada en tu cuenta Binance Demo: "
                    f"{side} {qty} {sym} (Order ID: {order.get('orderId')})"
                )
                # Dejar SL y TP alojados directamente en los servidores de Binance Demo (protección con PC apagado)
                exit_side = "SELL" if side == "LONG" else "BUY"
                if pos.get("stop_loss", 0) > 0:
                    try:
                        await conn.create_order(
                            symbol=sym, side=exit_side, positionSide=side,
                            order_type="STOP_MARKET", quantity=qty,
                            stopPrice=round(pos["stop_loss"], 2), closePosition=False
                        )
                    except Exception:
                        pass
                if pos.get("take_profit", 0) > 0:
                    try:
                        await conn.create_order(
                            symbol=sym, side=exit_side, positionSide=side,
                            order_type="TAKE_PROFIT_MARKET", quantity=qty,
                            stopPrice=round(pos["take_profit"], 2), closePosition=False
                        )
                    except Exception:
                        pass
            except Exception as e:
                pos["binance_demo_note"] = "Simulado localmente"
                if "-4411" in str(e):
                    sync_logs.append(f"[API DEMO BINANCE - {m}_TESTNET] {sym}: Pendiente aceptar acuerdo TradFi-Perps en web de Binance Demo (Simulado localmente)")
                elif "-1121" in str(e):
                    sync_logs.append(f"[API DEMO BINANCE - {m}_TESTNET] {sym}: Par exclusivo de Mainnet (Simulado localmente con precios reales)")
                else:
                    sync_logs.append(f"[API DEMO BINANCE - {m}_TESTNET] {sym}: Simulado localmente ({str(e)[:60]})")

    try:
        asyncio.run(_run_sync())
    except Exception as e:
        sync_logs.append(f"Error loop async sync: {e}")

    return sync_logs



def send_telegram_alert(text: str):
    """Envía alerta en tiempo real al bot de Telegram (@TrifectaTradingBot) si está configurado."""
    tok = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
    cid = os.getenv("TELEGRAM_CHAT_ID")
    if not tok or not cid:
        return
    try:
        data = urllib.parse.urlencode({"chat_id": cid, "text": text}).encode("utf-8")
        req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=data)
        urllib.request.urlopen(req, timeout=8)
    except Exception:
        pass


def fetch_binance_klines(symbol: str, interval: str, limit: int = 220) -> List:
    """Obtiene velas reales en vivo desde Binance Futures (sin necesidad de suscripción paga)."""
    params = urllib.parse.urlencode({"symbol": symbol, "interval": interval, "limit": limit})
    url = f"{BINANCE_FAPI_URL}/fapi/v1/klines?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "AntigravityTrifectaDemo/8.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_binance_price(symbol: str) -> float:
    """Obtiene el último precio en tiempo real desde Binance Futures."""
    params = urllib.parse.urlencode({"symbol": symbol})
    url = f"{BINANCE_FAPI_URL}/fapi/v1/ticker/price?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "AntigravityTrifectaDemo/8.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return float(data["price"])


def init_default_state() -> Dict:
    """Inicializa el portafolio Demo con $3,000 USD (Asignación V8.1: $600 B1 [20%], $1,200 B2 [40%], $1,200 B3 [40%])."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {
        "created_at": now_str,
        "last_updated": now_str,
        "scans_completed": 0,
        "global_regime": "NORMAL",
        "engines": {
            "B1": {
                "motor_id": B1SprintEngine.CONFIG["motor_id"],
                "name": "Grid Dinámico & Reversión en Rango (ADX < 25)",
                "symbols": B1SprintEngine.CONFIG["symbols"],
                "initial_capital": 600.0,
                "cash_balance": 600.0,
                "realized_pnl": 0.0,
                "wins": 0,
                "losses": 0,
                "open_positions": {},
                "closed_trades": []
            },
            "B2": {
                "motor_id": B2ResilienceEngine.CONFIG["motor_id"],
                "name": "Rotación Fuerza Relativa Multi-Activo (ROC 15d)",
                "symbols": B2ResilienceEngine.CONFIG["symbols"],
                "initial_capital": 1200.0,
                "cash_balance": 1200.0,
                "realized_pnl": 0.0,
                "wins": 0,
                "losses": 0,
                "open_positions": {},
                "closed_trades": []
            },
            "B3": {
                "motor_id": B3AnchorEngine.CONFIG["motor_id"],
                "name": "Bóveda Anti-Degradación Monetaria Wyckoff",
                "symbols": B3AnchorEngine.CONFIG["symbols"],
                "initial_capital": 1200.0,
                "cash_balance": 1200.0,
                "realized_pnl": 0.0,
                "wins": 0,
                "losses": 0,
                "open_positions": {},
                "closed_trades": []
            }
        }
    }


def load_state() -> Dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                st = json.load(f)
            if "engines" in st:
                st["engines"]["B1"]["symbols"] = B1SprintEngine.CONFIG["symbols"]
                st["engines"]["B2"]["symbols"] = B2ResilienceEngine.CONFIG["symbols"]
                st["engines"]["B3"]["symbols"] = B3AnchorEngine.CONFIG["symbols"]
            return st
        except Exception:
            pass
    state = init_default_state()
    save_state(state)
    return state


def save_state(state: Dict):
    state["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def update_and_check_positions(engine_key: str, eng_state: Dict, live_prices: Dict[str, float]) -> List[str]:
    """Actualiza PnL flotante, aplica Candado de Ganancias V8.1 (Auto-Breakeven & Escalón) y verifica SL/TP."""
    events = []
    to_close = []

    for sym, pos in eng_state["open_positions"].items():
        price = live_prices.get(sym, pos["entry_price"])
        pos["current_price"] = price
        side = pos["side"]
        entry = pos["entry_price"]
        qty = pos["quantity"]
        notional = pos["notional"]
        lev = max(1, int(pos.get("leverage", 2)))

        if side in ("LONG", "BUY"):
            raw_pnl = (price - entry) * qty
            hit_sl = pos["stop_loss"] > 0 and price <= pos["stop_loss"]
            hit_tp = pos["take_profit"] > 0 and price >= pos["take_profit"]
        else:
            raw_pnl = (entry - price) * qty
            hit_sl = pos["stop_loss"] > 0 and price >= pos["stop_loss"]
            hit_tp = pos["take_profit"] > 0 and price <= pos["take_profit"]

        fee_est = notional * TAKER_FEE * 2
        net_pnl = raw_pnl - fee_est
        pos["unrealized_pnl"] = round(net_pnl, 2)
        pnl_pct = round((net_pnl / pos["margin"]) * 100, 2) if pos["margin"] > 0 else 0.0
        pos["unrealized_pnl_pct"] = pnl_pct

        # ─── V8.2 MEJORA 1: COBRO PARCIAL 50% (+4.0% ROI) + CANDADO DE GANANCIAS ESCALONADO ───
        if not hit_tp and not hit_sl:
            # 1A. Si alcanza >= +4.0% sobre margen y aún no ha cobrado el 50% parcial, cobrar 50% a la caja
            if pnl_pct >= 4.0 and not pos.get("partial_tp_taken", False):
                half_pnl = round(net_pnl * 0.5, 2)
                half_qty = round(qty * 0.5, 4)
                half_margin = round(pos["margin"] * 0.5, 2)
                half_notional = round(notional * 0.5, 2)

                eng_state["cash_balance"] = round(eng_state["cash_balance"] + half_pnl, 2)
                eng_state["realized_pnl"] = round(eng_state["realized_pnl"] + half_pnl, 2)
                eng_state["wins"] += 1
                eng_state["closed_trades"].append({
                    "symbol": sym,
                    "side": side,
                    "entry_price": entry,
                    "exit_price": price,
                    "net_pnl": half_pnl,
                    "reason_entry": pos["reason"],
                    "reason_exit": "PARTIAL_TP_50%_V8.2",
                    "opened_at": pos["opened_at"],
                    "closed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })

                pos["quantity"] = round(qty - half_qty, 4)
                pos["margin"] = round(pos["margin"] - half_margin, 2)
                pos["notional"] = round(notional - half_notional, 2)
                pos["unrealized_pnl"] = round(net_pnl - half_pnl, 2)
                pos["partial_tp_taken"] = True
                qty = pos["quantity"]
                notional = pos["notional"]
                fee_est = notional * TAKER_FEE * 2

                events.append(
                    f"[{engine_key}] 💰 COBRO PARCIAL 50% V8.2 en {sym} {side} @ ${price:,.4f} -> "
                    f"Ganancia Embolsada: ${half_pnl:+,.2f} (50% restante corre libre)"
                )

            # 1B. Candado de Stop Loss sobre la posición restante
            old_sl = pos["stop_loss"]
            if pnl_pct >= 8.0:
                # Escalón 2 (+8% ROI sobre margen) -> Asegurar +4.5% sobre margen
                lock_move = 0.045 / lev
                if side in ("LONG", "BUY"):
                    new_sl = round(entry * (1.0 + lock_move), 4)
                    if new_sl > old_sl:
                        pos["stop_loss"] = new_sl
                        events.append(f"[{engine_key}] 🔒 CANDADO NIVEL 2 (+4.5% asegurado) en {sym} {side}: SL subido a ${new_sl:,.4f}")
                else:
                    new_sl = round(entry * (1.0 - lock_move), 4)
                    if old_sl == 0 or new_sl < old_sl:
                        pos["stop_loss"] = new_sl
                        events.append(f"[{engine_key}] 🔒 CANDADO NIVEL 2 (+4.5% asegurado) en {sym} {side}: SL bajado a ${new_sl:,.4f}")
            elif pnl_pct >= 4.0:
                # Escalón 1 (+4% ROI sobre margen) -> Asegurar Breakeven Positivo (+1.0% sobre margen)
                lock_move = 0.010 / lev
                if side in ("LONG", "BUY"):
                    new_sl = round(entry * (1.0 + lock_move), 4)
                    if new_sl > old_sl:
                        pos["stop_loss"] = new_sl
                        events.append(f"[{engine_key}] 🛡️ CANDADO BREAKEVEN (+1.0% asegurado) en {sym} {side}: SL protegido en ${new_sl:,.4f}")
                else:
                    new_sl = round(entry * (1.0 - lock_move), 4)
                    if old_sl == 0 or new_sl < old_sl:
                        pos["stop_loss"] = new_sl
                        events.append(f"[{engine_key}] 🛡️ CANDADO BREAKEVEN (+1.0% asegurado) en {sym} {side}: SL protegido en ${new_sl:,.4f}")

        if hit_tp:
            tp_p = pos["take_profit"]
            raw_tp = ((tp_p - entry) * qty) if side in ("LONG", "BUY") else ((entry - tp_p) * qty)
            to_close.append((sym, tp_p, "TAKE_PROFIT", raw_tp - fee_est))
        elif hit_sl:
            sl_p = pos["stop_loss"]
            raw_sl = ((sl_p - entry) * qty) if side in ("LONG", "BUY") else ((entry - sl_p) * qty)
            to_close.append((sym, sl_p, "STOP_LOSS", raw_sl - fee_est))

    for sym, close_price, close_reason, net_pnl in to_close:
        pos = eng_state["open_positions"].pop(sym)
        eng_state["cash_balance"] = round(eng_state["cash_balance"] + net_pnl, 2)
        eng_state["realized_pnl"] = round(eng_state["realized_pnl"] + net_pnl, 2)
        if net_pnl >= 0:
            eng_state["wins"] += 1
        else:
            eng_state["losses"] += 1

        trade_record = {
            "symbol": sym,
            "side": pos["side"],
            "entry_price": pos["entry_price"],
            "exit_price": close_price,
            "net_pnl": round(net_pnl, 2),
            "reason_entry": pos["reason"],
            "reason_exit": close_reason,
            "opened_at": pos["opened_at"],
            "closed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        eng_state["closed_trades"].append(trade_record)
        events.append(f"[{engine_key}] CERRADA {pos['side']} {sym} @ ${close_price:,.4f} ({close_reason}) -> PnL Neto: ${net_pnl:+,.2f}")

    return events


def open_demo_position(
    engine_key: str,
    eng_state: Dict,
    symbol: str,
    side: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    leverage: int,
    margin_pct: float,
    reason: str,
    max_open: int = 3
) -> Optional[str]:
    """Abre una posición virtual en la cuenta Demo del motor correspondiente."""
    if symbol in eng_state["open_positions"]:
        return None
    if len(eng_state["open_positions"]) >= max_open:
        return None

    margin = round(eng_state["cash_balance"] * (margin_pct / 100.0), 2)
    notional = round(margin * leverage, 2)
    qty = notional / entry_price if entry_price > 0 else 0.0
    if qty <= 0:
        return None

    norm_side = "LONG" if side in ("BUY", "LONG") else "SHORT"
    eng_state["open_positions"][symbol] = {
        "symbol": symbol,
        "side": norm_side,
        "entry_price": entry_price,
        "current_price": entry_price,
        "quantity": round(qty, 4),
        "margin": margin,
        "leverage": leverage,
        "notional": notional,
        "stop_loss": round(stop_loss, 4),
        "take_profit": round(take_profit, 4),
        "unrealized_pnl": 0.0,
        "unrealized_pnl_pct": 0.0,
        "reason": reason,
        "opened_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    return (
        f"[{engine_key}] NUEVA ENTRADA {norm_side} {symbol} @ ${entry_price:,.4f} | "
        f"Margen: ${margin:.0f} ({leverage}x = ${notional:.0f}) | "
        f"SL: ${stop_loss:,.4f} | TP: ${take_profit:,.4f} | {reason}"
    )


def run_live_scan(state: Dict, allow_watch_entry: bool = False) -> Dict:
    """
    Ejecuta un ciclo completo de los 3 motores B1, B2 y B3 contra Binance Futures en vivo.
    Retorna un diccionario con diagnósticos detallados por par y eventos ejecutados.
    """
    b1_strat = B1Strategy(B1SprintEngine.CONFIG)
    b2_strat = B2Strategy(B2ResilienceEngine.CONFIG)
    b3_strat = B3Strategy(B3AnchorEngine.CONFIG)

    live_prices: Dict[str, float] = {}
    diagnostics: Dict[str, List[Dict]] = {"B1": [], "B2": [], "B3": []}
    events: List[str] = []

    # ─── 1. ESCANEO MOTOR B3 (Primero para actualizar Intercomunicador GLOBAL_REGIME) ───
    b3_state = state["engines"]["B3"]
    for sym in B3AnchorEngine.CONFIG["symbols"]:
        try:
            klines_4h = fetch_binance_klines(sym, "4h", limit=210)
            klines_1d = fetch_binance_klines(sym, "1d", limit=210)
            price = float(klines_4h[-1][4])
            live_prices[sym] = price

            data_4h = {"symbol": sym, "klines": klines_4h, "timeframe": "4h"}
            data_1d = {"symbol": sym, "klines": klines_1d, "timeframe": "1d"}

            df_4h = b3_strat._prepare_df(klines_4h)
            rsi_4h = float(ind.calculate_rsi(df_4h["close"], 14).iloc[-1])
            z_4h = float(ind.calculate_zscore(df_4h["close"], 20).iloc[-1])

            sig = b3_strat.analyze(data_4h, data_1d)
            status_txt = "EN ESPERA (Vigilando Descuento Wyckoff)"
            if sig:
                status_txt = f"SEÑAL {sig.side}: {sig.reason}"
                if sig.side == "EXIT_LONG" and sym in b3_state["open_positions"]:
                    pos = b3_state["open_positions"].pop(sym)
                    raw_pnl = (price - pos["entry_price"]) * pos["quantity"]
                    net_pnl = raw_pnl - (pos["notional"] * TAKER_FEE * 2)
                    b3_state["cash_balance"] = round(b3_state["cash_balance"] + net_pnl, 2)
                    b3_state["realized_pnl"] = round(b3_state["realized_pnl"] + net_pnl, 2)
                    if net_pnl >= 0:
                        b3_state["wins"] += 1
                    else:
                        b3_state["losses"] += 1
                    events.append(f"[B3] SALIDA EN FORTALEZA {sym} @ ${price:,.2f} -> PnL: ${net_pnl:+,.2f}")
                elif sig.side == "LONG":
                    ev = open_demo_position(
                        "B3", b3_state, sym, "LONG", price,
                        sig.stop_loss, sig.take_profit,
                        leverage=2, margin_pct=20.0, reason=sig.reason, max_open=4
                    )
                    if ev:
                        events.append(ev)

            diagnostics["B3"].append({
                "symbol": sym,
                "price": price,
                "metric_1": f"RSI(4H): {rsi_4h:.1f}",
                "metric_2": f"Z-Score(4H): {z_4h:+.2f}",
                "filter": "RSI < 30.5 o Z < -1.80",
                "status": status_txt
            })
        except Exception as e:
            diagnostics["B3"].append({
                "symbol": sym, "price": 0.0,
                "metric_1": "ERR", "metric_2": str(e)[:30],
                "filter": "-", "status": "Error de conexión"
            })

    state["global_regime"] = getattr(B3AnchorEngine, "GLOBAL_REGIME", "NORMAL")
    events.extend(update_and_check_positions("B3", b3_state, live_prices))

    # ─── 2. ESCANEO MOTOR B2 (Primero B2 antes que B1 para actualizar conteo real de SHORTs y ROC 48h) ───
    b2_state = state["engines"]["B2"]
    b2_candidates = []
    for sym in B2ResilienceEngine.CONFIG["symbols"]:
        try:
            klines_1h = fetch_binance_klines(sym, "1h", limit=70)
            klines_4h = fetch_binance_klines(sym, "4h", limit=220)
            price = float(klines_1h[-1][4])
            live_prices[sym] = price

            closes_4h = [float(k[4]) for k in klines_4h]
            highs_4h = [float(k[2]) for k in klines_4h]
            lows_4h = [float(k[3]) for k in klines_4h]

            roc_2d = ((closes_4h[-1] / closes_4h[-12]) - 1.0) * 100.0 if len(closes_4h) >= 12 else 0.0
            roc_15d = ((closes_4h[-1] / closes_4h[-90]) - 1.0) * 100.0 if len(closes_4h) >= 90 else 0.0
            adx_4h = b2_strat._adx(highs_4h, lows_4h, closes_4h, 14)

            data_1h = {"symbol": sym, "klines": klines_1h, "price": price, "timeframe": "1h"}
            data_4h = {"symbol": sym, "klines": klines_4h, "price": price, "timeframe": "4h"}

            sig = b2_strat.analyze(data_1h, data_4h)
            if roc_15d < -4.0 and roc_2d >= 2.8:
                status_txt = f"FILTRO V-REBOTE 48H (+{roc_2d:.1f}% bloquea SHORT)"
            elif sig:
                status_txt = f"SEÑAL {sig.side.name} (Score {sig.strength:.2f}): {sig.reason}"
                b2_candidates.append((max(abs(roc_15d), abs(roc_2d)), sig))
            else:
                status_txt = f"Monitoreando (ROC15d={roc_15d:+.1f}%, 48h={roc_2d:+.1f}%)"

            diagnostics["B2"].append({
                "symbol": sym,
                "price": price,
                "metric_1": f"ROC15d:{roc_15d:+.1f}%",
                "metric_2": f"48h:{roc_2d:+.1f}% | ADX:{adx_4h:.1f}",
                "filter": "ADX > 18 & Anti-V 48h",
                "status": status_txt
            })
        except Exception as e:
            diagnostics["B2"].append({
                "symbol": sym, "price": 0.0,
                "metric_1": "ERR", "metric_2": str(e)[:30],
                "filter": "-", "status": "Error de conexión"
            })

    # Primero actualizar y aplicar Cobro Parcial 50% + Candados V8.2 en B2 antes de evaluar nuevos cupos y antes de correr B1
    events.extend(update_and_check_positions("B2", b2_state, live_prices))

    # Ordenar candidatos de B2 por mayor Fuerza Relativa para entrar primero en los líderes
    b2_candidates.sort(key=lambda x: x[0], reverse=True)
    for _, sig in b2_candidates:
        ev = open_demo_position(
            "B2", b2_state, sig.symbol, sig.side.name, sig.entry_price,
            sig.stop_loss, sig.take_profit,
            leverage=sig.leverage, margin_pct=20.0, reason=sig.reason, max_open=4
        )
        if ev:
            events.append(ev)

    # ─── 3. ESCANEO MOTOR B1 (Grid Dinámico & Reversión en Rango ADX < 25 + Escudo Bajista B2) ───
    b1_state = state["engines"]["B1"]
    b2_active_shorts = sum(1 for p in b2_state["open_positions"].values() if p.get("side") == "SHORT")
    b1_strat.b2_bear_shield = (b2_active_shorts >= 3)

    for sym in B1SprintEngine.CONFIG["symbols"]:
        try:
            klines_5m = fetch_binance_klines(sym, "5m", limit=100)
            klines_15m = fetch_binance_klines(sym, "15m", limit=100)
            price = float(klines_5m[-1][4])
            live_prices[sym] = price

            closes_15m = [float(k[4]) for k in klines_15m]
            highs_15m = [float(k[2]) for k in klines_15m]
            lows_15m = [float(k[3]) for k in klines_15m]
            adx_15m = b1_strat._adx(highs_15m, lows_15m, closes_15m, 14)
            z_15m = b1_strat._zscore(closes_15m, 20)
            rsi_5m = b1_strat._rsi([float(k[4]) for k in klines_5m], 14)

            data_5m = {"symbol": sym, "klines": klines_5m, "price": price}
            data_15m = {"symbol": sym, "klines": klines_15m, "price": price}

            sig = b1_strat.analyze(data_5m, data_15m)
            if adx_15m >= 25.0:
                status_txt = f"PAUSADO POR TENDENCIA FUERTE (ADX {adx_15m:.1f} >= 25)"
            elif b1_strat.b2_bear_shield:
                status_txt = f"ESCUDO BAJISTA B2 ACTIVO ({b2_active_shorts} SHORTs en B2 bloquean LONGs)"
            elif sig:
                status_txt = f"SEÑAL {sig.side.name}: {sig.reason}"
                ev = open_demo_position(
                    "B1", b1_state, sym, sig.side.name, price,
                    sig.stop_loss, sig.take_profit,
                    leverage=3, margin_pct=20.0, reason=sig.reason, max_open=3
                )
                if ev:
                    events.append(ev)
            else:
                status_txt = f"RANGO ACTIVO (Esperando |Z|>=1.45, actual {z_15m:+.2f})"

            diagnostics["B1"].append({
                "symbol": sym,
                "price": price,
                "metric_1": f"ADX(15m): {adx_15m:.1f}",
                "metric_2": f"Z(15m): {z_15m:+.2f} | RSI(5m): {rsi_5m:.1f}",
                "filter": "ADX < 25 & |Z| >= 1.45",
                "status": status_txt
            })
        except Exception as e:
            diagnostics["B1"].append({
                "symbol": sym, "price": 0.0,
                "metric_1": "ERR", "metric_2": str(e)[:30],
                "filter": "-", "status": "Error de conexión"
            })

    events.extend(update_and_check_positions("B1", b1_state, live_prices))

    # ─── 4. SINCRONIZAR CON LAS 3 API KEYS DE BINANCE DEMO TRADING (B1/B2/B3_TESTNET) ───
    sync_events = sync_positions_to_binance_demo_api(state)
    events.extend(sync_events)

    if events:
        tg_msg = "⚡ ACTUALIZACIÓN DEMO TRIFECTA V8.2:\n" + "\n".join(f"• {e}" for e in events[:8])
        send_telegram_alert(tg_msg)

    state["scans_completed"] = state.get("scans_completed", 0) + 1
    save_state(state)
    return {"diagnostics": diagnostics, "events": events}


def print_dashboard(state: Dict, scan_result: Optional[Dict] = None):
    """Imprime el panel ejecutivo de la Demo en consola."""
    print("\n" + "═" * 100)
    print(f"🏦 PANEL DEMO EN VIVO BINANCE FUTURES — ARQUITECTURA TRIFECTA 2026 (V8.2 CARTERA PROPIA)")
    print(f"🕒 Actualizado: {state['last_updated']} | Escaneos: {state['scans_completed']} | Régimen Macro B3: {state.get('global_regime', 'NORMAL')}")
    print("═" * 100)

    total_initial = 0.0
    total_equity = 0.0
    total_open = 0

    for key in ("B1", "B2", "B3"):
        eng = state["engines"][key]
        init_cap = eng["initial_capital"]
        cash = eng["cash_balance"]
        unrealized = sum(p.get("unrealized_pnl", 0.0) for p in eng["open_positions"].values())
        equity = cash + unrealized
        roi_pct = ((equity - init_cap) / init_cap) * 100.0
        total_initial += init_cap
        total_equity += equity
        total_open += len(eng["open_positions"])
        max_slots = 3 if key == "B1" else 4

        print(
            f"🔹 {key} [{eng['motor_id']}] — {eng['name']}\n"
            f"   Capital Base: ${init_cap:,.2f} | Equity Actual: ${equity:,.2f} ({roi_pct:+.2f}%) | "
            f"PnL Realizado: ${eng['realized_pnl']:+,.2f} | PnL Flotante: ${unrealized:+,.2f} | "
            f"W/L: {eng['wins']}/{eng['losses']} | Posiciones Abiertas: {len(eng['open_positions'])}/{max_slots}"
        )
        if eng["open_positions"]:
            for sym, p in eng["open_positions"].items():
                print(
                    f"      👉 [{p['side']}] {sym}: Entrada ${p['entry_price']:,.4f} -> Actual ${p['current_price']:,.4f} | "
                    f"Margen ${p['margin']:.0f} ({p['leverage']}x) | SL ${p['stop_loss']:,.4f} | TP ${p['take_profit']:,.4f} | "
                    f"PnL: ${p['unrealized_pnl']:+,.2f} ({p['unrealized_pnl_pct']:+.2f}%) [{p['reason']}]"
                )
        print("-" * 100)

    total_roi = ((total_equity - total_initial) / total_initial) * 100.0 if total_initial > 0 else 0.0
    print(
        f"💰 TOTAL PORTAFOLIO DEMO TRIFECTA: ${total_equity:,.2f} / ${total_initial:,.2f} "
        f"({total_roi:+.2f}%) | Posiciones Activas Totales: {total_open}"
    )
    print("═" * 100)

    if scan_result:
        if scan_result["events"]:
            print("\n⚡ EVENTOS Y ÓRDENES EJECUTADAS EN ESTE CICLO:")
            for ev in scan_result["events"]:
                print(f"   ✅ {ev}")
        else:
            print("\nℹ️ Sin cierres ni nuevas aperturas en este segundo exacto.")

        print("\n📡 RADAR EN TIEMPO REAL DE LOS 16 ACTIVOS EN BINANCE FUTURES (V8.2):")
        for key in ("B1", "B2", "B3"):
            print(f"\n  [{key} — {state['engines'][key]['motor_id']}]")
            for d in scan_result["diagnostics"][key]:
                print(
                    f"    • {d['symbol']:<11} | Precio: ${d['price']:>10,.4f} | "
                    f"{d['metric_1']:<18} | {d['metric_2']:<28} | {d['status']}"
                )
    print("\n")


def _send_tg_message(tok: str, chat_id: str, text: str):
    """Envía mensaje a Telegram con fallback automático a texto plano si falla el parseo Markdown."""
    for use_md in (True, False):
        try:
            payload = {"chat_id": chat_id, "text": text if use_md else text.replace("*", "").replace("_", "").replace("`", "")}
            if use_md:
                payload["parse_mode"] = "Markdown"
            data = urllib.parse.urlencode(payload).encode("utf-8")
            req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=data)
            urllib.request.urlopen(req, timeout=10)
            return
        except Exception:
            continue


def _build_demo_telegram_text(state: Dict) -> str:
    lines = [
        "🏦 *PORTAFOLIO DEMO TRIFECTA V8.2 (CARTERA PROPIA)*",
        f"🕒 `{state['last_updated']}` | Escaneos: `{state.get('scans_completed', 0)}` | Régimen: *{state.get('global_regime', 'NORMAL')}*\n"
    ]
    tot_init, tot_eq = 0.0, 0.0
    for k in ("B1", "B2", "B3"):
        eng = state["engines"][k]
        unr = sum(p.get("unrealized_pnl", 0.0) for p in eng["open_positions"].values())
        eq = eng["cash_balance"] + unr
        roi = ((eq - eng["initial_capital"]) / eng["initial_capital"]) * 100.0
        tot_init += eng["initial_capital"]
        tot_eq += eq
        max_slots = 3 if k == "B1" else 4
        lines.append(f"🔹 *{k}* (`{eng['motor_id']}`): `${eq:,.2f}` (`{roi:+.2f}%`) | Abiertas: `{len(eng['open_positions'])}/{max_slots}`")
        for sym, p in eng["open_positions"].items():
            ptp_tag = " `[50% Cobrado 💰]`" if p.get("partial_tp_taken") else ""
            lines.append(
                f"   • `{p['side']}` *{sym}*{ptp_tag}: `${p['entry_price']:,.4f}` → `${p['current_price']:,.4f}` "
                f"| SL: `${p['stop_loss']:,.4f}` | PnL: `${p['unrealized_pnl']:+,.2f}` (`{p['unrealized_pnl_pct']:+.2f}%`)"
            )
    tot_roi = ((tot_eq - tot_init) / tot_init) * 100.0 if tot_init > 0 else 0.0
    lines.append(f"\n💰 *TOTAL EQUITY DEMO*: `${tot_eq:,.2f}` / `${tot_init:,.2f}` (`{tot_roi:+.2f}%`)")
    return "\n".join(lines)


def _build_tendencia_telegram_text() -> str:
    """Calcula el análisis Bull/Bear macro de BTCUSDT y ETHUSDT (4 indicadores en 4H)."""
    lines = [
        "📊 *ANÁLISIS DE TENDENCIA MACRO (4H)*",
        f"⏰ `{datetime.now().strftime('%Y-%m-%d %H:%M')}`\n"
    ]
    b1_s = B1Strategy(B1SprintEngine.CONFIG)
    scores = []
    for sym in ("BTCUSDT", "ETHUSDT"):
        kl = fetch_binance_klines(sym, "4h", limit=210)
        closes = [float(x[4]) for x in kl]
        highs = [float(x[2]) for x in kl]
        lows = [float(x[3]) for x in kl]
        price = closes[-1]
        ema50 = b1_s._ema(closes, 50)
        ema200 = b1_s._ema(closes, 200)
        rsi = b1_s._rsi(closes, 14)
        adx = b1_s._adx(highs, lows, closes, 14)

        score = 0
        if price > ema200:
            score += 35
        if ema50 > ema200:
            score += 30
        if rsi > 50:
            score += 20
        if adx > 25 and price > ema50:
            score += 15
        scores.append(score)
        reg = "BULL 🟢" if score >= 50 else "BEAR 🔴"
        lines.append(
            f"*{sym}* — {reg} (`{score}/100`)\n"
            f"  💲 Precio: `${price:,.2f}` | EMA50: `${ema50:,.2f}` | EMA200: `${ema200:,.2f}`\n"
            f"  📈 RSI(4H): `{rsi:.1f}` | ADX(4H): `{adx:.1f}`\n"
        )
    avg_s = sum(scores) / len(scores) if scores else 50
    g_reg = "BULL 🟢" if avg_s >= 50 else "BEAR 🔴"
    lines.append(f"🌐 *CLIMA GLOBAL CRIPTO*: *{g_reg}* (Score `{avg_s:.0f}/100`)")
    return "\n".join(lines)


def process_pending_telegram_commands(offset_holder: List[int]):
    """Lee y responde todos los comandos enviados al bot @TrifectaTradingBot (/demo, /analista, /tendencia, etc.)."""
    tok = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
    if not tok:
        return
    try:
        params = {"timeout": 1}
        if offset_holder[0] > 0:
            params["offset"] = offset_holder[0]
        url = f"https://api.telegram.org/bot{tok}/getUpdates?{urllib.parse.urlencode(params)}"
        data = json.loads(urllib.request.urlopen(url, timeout=6).read().decode("utf-8"))
        for upd in data.get("result", []):
            offset_holder[0] = upd["update_id"] + 1
            msg = upd.get("message") or upd.get("edited_message") or {}
            text = (msg.get("text") or "").strip()
            chat_id = str(msg.get("chat", {}).get("id", ""))
            if not text or not chat_id:
                continue

            cmd = text.split()[0].lower().split("@")[0]
            if cmd in ("/demo", "/status", "/positions", "/pnl", "/balance"):
                _send_tg_message(tok, chat_id, "📡 *Actualizando precios en vivo de los 16 activos en Binance Futures (V8.2)...*")
                st = load_state()
                run_live_scan(st)
                _send_tg_message(tok, chat_id, _build_demo_telegram_text(st))
            elif cmd == "/analista":
                _send_tg_message(tok, chat_id, "🏛️ *Ejecutando Escáner Institucional Multi-Activo (Macro, Cripto, Commodities y Acciones)...*")
                from core.senior_analyst import SeniorMarketAnalyst
                report = SeniorMarketAnalyst().generate_executive_report()
                _send_tg_message(tok, chat_id, report)
            elif cmd == "/tendencia":
                _send_tg_message(tok, chat_id, _build_tendencia_telegram_text())
            elif cmd in ("/start", "/help", "/report", "/metrics"):
                help_txt = (
                    "🚀 *ANTIGRAVITY TRIFECTA V8 — PANEL DE CONTROL TELEGRAM*\n\n"
                    "Comandos activos en tiempo real:\n"
                    "• /demo — 🏦 Estado en vivo del Portafolio Demo V8 ($3,000) y las 6 posiciones\n"
                    "• /analista — 🏛️ Informe Senior (Macro, DXY, US10Y, Cripto, Oro, Plata, Cobre, S&P 500)\n"
                    "• /tendencia — 📈 Diagnóstico Bull/Bear en 4H (BTC + ETH)\n"
                    "• /positions — 📊 Ver posiciones abiertas y PnL flotante\n"
                    "• /balance — 💰 Ver capital y retorno acumulado por motor"
                )
                _send_tg_message(tok, chat_id, help_txt)
        if data.get("result") and offset_holder[0] > 0:
            ack_url = f"https://api.telegram.org/bot{tok}/getUpdates?offset={offset_holder[0]}&timeout=0"
            urllib.request.urlopen(ack_url, timeout=5).read()
    except Exception:
        pass


def start_telegram_listener_thread():
    """Inicia un hilo en segundo plano que responde en <2 segundos a los comandos de Telegram."""
    import threading
    offset_holder = [0]

    def _worker():
        while True:
            process_pending_telegram_commands(offset_holder)
            time.sleep(2)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def main():
    parser = argparse.ArgumentParser(description="Demo En Vivo Binance Futures — Trifecta 2026 (B1, B2, B3)")
    parser.add_argument("--once", action="store_true", help="Ejecuta un escaneo en vivo único y muestra el radar")
    parser.add_argument("--loop", action="store_true", help="Mantiene los 3 motores corriendo en vivo cada N segundos")
    parser.add_argument("--interval", type=int, default=300, help="Segundos entre cada escaneo en modo --loop (default: 300s = 5m)")
    parser.add_argument("--status", action="store_true", help="Muestra el estado actual del portafolio Demo")
    parser.add_argument("--reset", action="store_true", help="Reinicia el portafolio Demo a $3,000 USD ($1,000 por motor)")
    args = parser.parse_args()

    if args.reset:
        state = init_default_state()
        save_state(state)
        print("✅ Portafolio Demo reiniciado a $3,000.00 USD ($1,000.00 en B1, B2 y B3).")
        print_dashboard(state)
        return

    state = load_state()

    if args.status:
        print_dashboard(state)
        return

    if args.loop:
        print(f"🚀 Iniciando DEMO EN VIVO 24/7 + Bot Telegram (@TrifectaTradingBot) en Binance Futures (Intervalo: {args.interval}s)...")
        start_telegram_listener_thread()
        try:
            while True:
                res = run_live_scan(state)
                print_dashboard(state, res)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n🛑 Demo en vivo pausada por el usuario. El estado quedó guardado en demo_portfolio_state.json.")
        return

    # Procesar cualquier comando pendiente en Telegram también en modo --once
    process_pending_telegram_commands([0])
    res = run_live_scan(state)
    print_dashboard(state, res)


if __name__ == "__main__":
    main()

