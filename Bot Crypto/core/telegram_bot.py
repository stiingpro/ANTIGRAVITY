import os
import math
import logging
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

logger = logging.getLogger('Core.Telegram')

# ─── Backtest Baseline Metrics (validated Walk-Forward + Stress Test) ───
BACKTEST_METRICS = {
    'B1': {
        'name': 'B1 Sprint', 'tf': '5m', 'style': 'Agresivo',
        'symbols': ['SOLUSDT'],
        'phase_a': {'roi': 56.0, 'pnl': 672.0, 'wr': 59.8, 'sharpe': 1.85, 'mdd': 8.3, 'pf': 1.23, 'trades': 87},
        'phase_b': {'roi': 45.2, 'pnl': 1356.0, 'wr': 58.5, 'sharpe': 1.62, 'mdd': 11.6, 'pf': 1.18, 'trades': 142},
    },
    'B2': {
        'name': 'B2 Resilience', 'tf': '1H', 'style': 'Moderado',
        'symbols': ['SOLUSDT', 'AVAXUSDT', 'DOTUSDT', 'ETHUSDT'],
        'phase_a': {'roi': 46.2, 'pnl': 462.0, 'wr': 59.6, 'sharpe': 1.42, 'mdd': 7.9, 'pf': 1.10, 'trades': 120},
        'phase_b': {'roi': 180.0, 'pnl': 1800.0, 'wr': 60.9, 'sharpe': 1.15, 'mdd': 12.0, 'pf': 1.15, 'trades': 195},
    },
    'B3': {
        'name': 'B3 Anchor', 'tf': '4H/1D', 'style': 'Conservador',
        'symbols': ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'LINKUSDT', 'DOTUSDT'],
        'phase_a': {'roi': 32.5, 'pnl': 325.0, 'wr': 55.0, 'sharpe': 2.10, 'mdd': 6.5, 'pf': 1.22, 'trades': 45},
        'phase_b': {'roi': -2.0, 'pnl': -20.0, 'wr': 48.0, 'sharpe': 0.55, 'mdd': 18.0, 'pf': 0.95, 'trades': 38},
    }
}


class TelegramInterface:
    """
    Interfaz de Control y Alertas (Telegram).
    Comandos: start, help, status, balance, positions, report, metrics, risk, pnl, sharpe, kill
    """
    def __init__(self, orchestrator):
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        self.orchestrator = orchestrator
        self.bot = None
        self.dp = None
        self.polling_task = None
        self.start_time = datetime.utcnow()

    async def start(self):
        if not self.token:
            logger.warning("⚠️ Telegram Token no encontrado. Bot DESACTIVADO.")
            return

        self.bot = Bot(token=self.token)
        self.dp = Dispatcher()
        
        # ─── Registrar TODOS los comandos ───
        commands = [
            ("start", self.cmd_start),
            ("help", self.cmd_help),
            ("status", self.cmd_status),
            ("balance", self.cmd_balance),
            ("positions", self.cmd_positions),
            ("report", self.cmd_report),
            ("metrics", self.cmd_metrics),
            ("risk", self.cmd_risk),
            ("pnl", self.cmd_pnl),
            ("sharpe", self.cmd_sharpe),
            ("kill", self.cmd_kill),
            ("local_positions", self.cmd_positions), # ALIAS LOCAL PARA BYPASS RAILWAY
            ("closeb1", self.cmd_closeb1),
            ("closeb2", self.cmd_closeb2),
            ("closeb3", self.cmd_closeb3),
            ("tendencia", self.cmd_tendencia),
        ]
        for cmd_name, handler in commands:
            self.dp.message(Command(cmd_name))(handler)

        logger.info("🤖 Telegram Bot Iniciado (11 comandos registrados).")
        
        self.polling_task = asyncio.create_task(self.dp.start_polling(self.bot))
        await self.send_alert("🚀 **Antigravity Trifecta V1** Iniciada en Railway.")

    async def stop(self):
        if self.polling_task:
            self.polling_task.cancel()
        if self.bot:
            await self.bot.session.close()

    async def send_alert(self, message: str):
        if self.bot and self.chat_id:
            try:
                await self.bot.send_message(self.chat_id, message, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"❌ Error enviando alerta TG: {e}")

    def _uptime(self):
        delta = datetime.utcnow() - self.start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{hours}h {minutes}m"

    # ═══════════════════════════════════════════════════
    #  COMANDOS BÁSICOS
    # ═══════════════════════════════════════════════════

    async def cmd_start(self, message: types.Message):
        await message.answer(
            "🚀 *Antigravity Trifecta Bot*\n\n"
            "Bot de trading automático con 3 motores:\n"
            "• B1 Sprint (5m) — Agresivo\n"
            "• B2 Resilience (1h) — Moderado\n"
            "• B3 Anchor (4h) — Conservador\n\n"
            "Usa /help para ver todos los comandos.",
            parse_mode="Markdown"
        )

    async def cmd_help(self, message: types.Message):
        await message.answer(
            "📋 *COMANDOS DISPONIBLES*\n\n"
            "📊 *Monitoreo:*\n"
            "/status — Estado de motores\n"
            "/balance — Balance detallado\n"
            "/positions — Posiciones abiertas\n\n"
            "📈 *Métricas e Informes:*\n"
            "/report — Informe ejecutivo completo\n"
            "/metrics — Tabla de métricas por motor\n"
            "/pnl — P&L desglosado\n"
            "/sharpe — Sharpe y Profit Factor\n"
            "/risk — Análisis de riesgo (MDD)\n\n"
            "⚠️ *Control:*\n"
            "/kill — 🛑 Emergencia: Detener todo\n"
            "/closeb1 — 🏎 Cerrar posiciones de B1\n"
            "/closeb2 — 🛡 Cerrar posiciones de B2\n"
            "/closeb3 — ⚓ Cerrar posiciones de B3\n\n"
            "🔍 *Análisis:*\n"
            "/tendencia — 📈 Anal. Bull/Bear (BTC+ETH)",
            parse_mode="Markdown"
        )

    async def cmd_status(self, message: types.Message):
        try:
            status_report = self.orchestrator.get_status_report()
            uptime = self._uptime()
            await message.answer(
                f"{status_report}\nUptime: {uptime}",
                parse_mode="Markdown"
            )
        except Exception as e:
            await message.answer(f"❌ Error: {e}")

    async def cmd_balance(self, message: types.Message):
        try:
            bal = self.orchestrator.connector.get_balance()
            if bal:
                total = float(bal.get('total', 0))
                available = float(bal.get('available', 0))
                pnl = float(bal.get('unrealized_pnl', 0))
                emoji = '🟢' if pnl >= 0 else '🔴'
                await message.answer(
                    f"💰 *BALANCE TRIFECTA*\n\n"
                    f"Total: `${total:.2f}` USDT\n"
                    f"Disponible: `${available:.2f}` USDT\n"
                    f"{emoji} PnL No Realizado: `${pnl:.2f}` USDT",
                    parse_mode="Markdown"
                )
            else:
                await message.answer("⚠️ No se pudo obtener el balance.")
        except Exception as e:
            await message.answer(f"❌ Error: {e}")

    async def cmd_positions(self, message: types.Message):
        try:
            positions = self.orchestrator.connector.get_open_positions()
            if not positions:
                await message.answer("📊 No hay posiciones abiertas.")
                return

            lines = [f"📊 *POSICIONES ABIERTAS ({len(positions)}) [LOCAL-DEBUG]*\n"]
            
            # Helper to identify source
            def get_source_tag(symbol):
                # Heuristic: SOLUSDT is B1 Priority (ALWAYS)
                if str(symbol).strip().upper() == 'SOLUSDT':
                    return "🏎 B1"

                # Heuristic: DOTUSDT/AVAXUSDT is B2 Priority
                if str(symbol).strip().upper() in ['DOTUSDT', 'AVAXUSDT']:
                    return "🛡 B2"

                # Check B1
                if self.orchestrator.b1.position_manager and \
                   symbol in self.orchestrator.b1.position_manager.active_positions:
                    return "🏎 B1"
                
                # Check B2
                if self.orchestrator.b2.position_manager and \
                   self.orchestrator.b2.position_manager.has_position(symbol):
                    return "🛡 B2"
                
                # Check B3 (Assumption: active if matches symbol list)
                if symbol in self.orchestrator.b3.CONFIG['symbols']:
                    return "⚓ B3"
                
                return "❓ Manual"

            for p in positions:
                emoji = '🟢' if p['pnl'] >= 0 else '🔴'
                tag = get_source_tag(p['symbol'])
                
                # DEBUG LINE (Force Error Level for visibility)
                logger.error(f"🔍 TELEGRAM DEBUG: Symbol='{p['symbol']}' -> Tag='{tag}'")

                lines.append(
                    f"{emoji} *{p['symbol']}* {p['side']}  {tag}\n"
                    f"   Entry: `${p['entry_price']:.4f}`\n"
                    f"   Qty: `{p['quantity']}`  x{p['leverage']}\n"
                    f"   PnL: `${p['pnl']:.2f}`"
                )
            await message.answer("\n".join(lines), parse_mode="Markdown")
        except Exception as e:
            await message.answer(f"❌ Error: {e}")

    # ═══════════════════════════════════════════════════
    #  COMANDOS DE MÉTRICAS E INFORMES
    # ═══════════════════════════════════════════════════

    async def cmd_report(self, message: types.Message):
        """Informe ejecutivo completo."""
        try:
            bal = self.orchestrator.connector.get_balance()
            total = float(bal.get('total', 0)) if bal else 0
            uptime = self._uptime()

            # Build summary from backtest + live
            b1 = BACKTEST_METRICS['B1']['phase_a']
            b2 = BACKTEST_METRICS['B2']['phase_a']
            b3 = BACKTEST_METRICS['B3']['phase_a']

            text = (
                f"📊 *INFORME EJECUTIVO TRIFECTA*\n"
                f"Fecha: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC\n"
                f"Uptime: {uptime}\n\n"
                f"💰 *Balance Actual:* `${total:.2f}` USDT\n\n"
                f"*─── Rendimiento Esperado (Backtest) ───*\n\n"
                f"🏎 *B1 Sprint* (SOL 5m)\n"
                f"  ROI: `+{b1['roi']}%` | WR: `{b1['wr']}%`\n"
                f"  Sharpe: `{b1['sharpe']}` | MDD: `{b1['mdd']}%`\n\n"
                f"🛡 *B2 Resilience* (Multi 1H)\n"
                f"  ROI: `+{b2['roi']}%` | WR: `{b2['wr']}%`\n"
                f"  Sharpe: `{b2['sharpe']}` | MDD: `{b2['mdd']}%`\n\n"
                f"⚓ *B3 Anchor* (Institucional 4H)\n"
                f"  ROI: `+{b3['roi']}%` | WR: `{b3['wr']}%`\n"
                f"  Sharpe: `{b3['sharpe']}` | MDD: `{b3['mdd']}%`\n\n"
                f"🔒 Kill Switch: -15% (B1) / -12% (B2) / -20% (B3)"
            )
            await message.answer(text, parse_mode="Markdown")
        except Exception as e:
            await message.answer(f"❌ Error: {e}")

    async def cmd_metrics(self, message: types.Message):
        """Tabla de métricas clave por motor."""
        lines = [
            "📈 *MÉTRICAS POR MOTOR*",
            "_(Backtest Walk-Forward 2023-2026)_\n",
        ]
        for key in ['B1', 'B2', 'B3']:
            m = BACKTEST_METRICS[key]
            pa = m['phase_a']
            emoji = '🏎' if key == 'B1' else ('🛡' if key == 'B2' else '⚓')
            lines.append(
                f"{emoji} *{m['name']}* ({m['tf']})\n"
                f"  ROI: `+{pa['roi']}%`\n"
                f"  Win Rate: `{pa['wr']}%`\n"
                f"  Sharpe: `{pa['sharpe']}`\n"
                f"  Max DD: `{pa['mdd']}%`\n"
                f"  PF: `{pa['pf']}`\n"
                f"  Trades: `{pa['trades']}`\n"
            )
        lines.append("Usa /risk para ver stress test")
        await message.answer("\n".join(lines), parse_mode="Markdown")

    async def cmd_pnl(self, message: types.Message):
        """P&L desglosado por motor y live."""
        try:
            bal = self.orchestrator.connector.get_balance()
            total = float(bal.get('total', 0)) if bal else 0
            pnl_live = float(bal.get('unrealized_pnl', 0)) if bal else 0
            initial = 5000.0  # Capital inicial Testnet
            
            live_roi = ((total - initial) / initial) * 100 if initial > 0 else 0
            emoji_live = '🟢' if live_roi >= 0 else '🔴'

            text = (
                f"💹 *P&L TRIFECTA*\n\n"
                f"*── Live (Testnet) ──*\n"
                f"Capital Inicial: `${initial:,.2f}`\n"
                f"Balance Actual: `${total:.2f}`\n"
                f"{emoji_live} ROI Live: `{live_roi:+.2f}%`\n"
                f"PnL No Realizado: `${pnl_live:.2f}`\n\n"
                f"*── Backtest Esperado (Fase A) ──*\n"
            )
            total_bt_pnl = 0
            for key in ['B1', 'B2', 'B3']:
                m = BACKTEST_METRICS[key]
                pa = m['phase_a']
                total_bt_pnl += pa['pnl']
                emoji = '🏎' if key == 'B1' else ('🛡' if key == 'B2' else '⚓')
                text += (
                    f"{emoji} {m['name']}: `+${pa['pnl']:.0f}` ({pa['roi']:+.1f}%)\n"
                )
            text += f"\n📊 Total Esperado: `+${total_bt_pnl:.0f}` USDT"

            await message.answer(text, parse_mode="Markdown")
        except Exception as e:
            await message.answer(f"❌ Error: {e}")

    async def cmd_sharpe(self, message: types.Message):
        """Sharpe Ratio y Profit Factor detallados."""
        lines = [
            "📏 *SHARPE & PROFIT FACTOR*\n",
            "```",
            f"{'Motor':<16} {'Sharpe':>7} {'PF':>6}  {'Fase':>6}",
            f"{'-'*40}",
        ]
        for key in ['B1', 'B2', 'B3']:
            m = BACKTEST_METRICS[key]
            pa = m['phase_a']
            pb = m['phase_b']
            lines.append(f"{m['name']:<16} {pa['sharpe']:>7.2f} {pa['pf']:>6.2f}  {'Bull':>6}")
            lines.append(f"{'':16} {pb['sharpe']:>7.2f} {pb['pf']:>6.2f}  {'Bear':>6}")
        lines.append("```")
        lines.append("\n✅ Sharpe > 1.0 = Eficiente")
        lines.append("✅ PF > 1.0 = Rentable")

        await message.answer("\n".join(lines), parse_mode="Markdown")

    async def cmd_risk(self, message: types.Message):
        """Análisis de riesgo: MDD actual vs histórico."""
        try:
            bal = self.orchestrator.connector.get_balance()
            total = float(bal.get('total', 0)) if bal else 0
            initial = 5000.0
            
            # Current drawdown from peak (simplified: from initial)
            current_dd = min(0, ((total - initial) / initial) * 100)
            
            text = (
                f"🛡 *ANÁLISIS DE RIESGO*\n\n"
                f"*── MDD Actual ──*\n"
                f"Drawdown: `{current_dd:.1f}%`\n"
                f"Kill Switch B1: `-15%`\n"
                f"Kill Switch B2: `-12%`\n"
                f"Kill Switch B3: `-20%`\n\n"
                f"*── MDD Histórico (Backtest) ──*\n"
                f"```\n"
                f"{'Motor':<16} {'Bull':>6} {'Bear':>6} {'Límite':>7}\n"
                f"{'-'*38}\n"
            )
            limits = {'B1': '15%', 'B2': '12%', 'B3': '20%'}
            for key in ['B1', 'B2', 'B3']:
                m = BACKTEST_METRICS[key]
                pa = m['phase_a']
                pb = m['phase_b']
                text += f"{m['name']:<16} {pa['mdd']:>5.1f}% {pb['mdd']:>5.1f}% {limits[key]:>7}\n"
            text += "```\n"

            # Risk level indicator
            if abs(current_dd) < 5:
                risk_emoji = "🟢"
                risk_level = "BAJO"
            elif abs(current_dd) < 10:
                risk_emoji = "🟡"
                risk_level = "MODERADO"
            else:
                risk_emoji = "🔴"
                risk_level = "ALTO"

            text += f"\n{risk_emoji} Nivel de Riesgo: *{risk_level}*"
            await message.answer(text, parse_mode="Markdown")
        except Exception as e:
            await message.answer(f"❌ Error: {e}")

    # ═══════════════════════════════════════════════════
    #  CONTROL
    # ═══════════════════════════════════════════════════

    async def cmd_kill(self, message: types.Message):
        """PANIC BUTTON: Detiene todo."""
        await message.answer("🛑 *KILL SWITCH ACTIVADO* 🛑\nDeteniendo motores...", parse_mode="Markdown")
        await self.orchestrator.emergency_stop("Manual Kill via Telegram")

    async def cmd_closeb1(self, message: types.Message):
        """Cerrar todas las posiciones de B1"""
        await self._close_by_bot(message, "B1")

    async def cmd_closeb2(self, message: types.Message):
        """Cerrar todas las posiciones de B2"""
        await self._close_by_bot(message, "B2")

    async def cmd_closeb3(self, message: types.Message):
        """Cerrar todas las posiciones de B3"""
        await self._close_by_bot(message, "B3")

    async def _close_by_bot(self, message: types.Message, target_bot: str):
        """Lógica común para cerrar posiciones por bot"""
        try:
            positions = self.orchestrator.connector.get_open_positions()
            if not positions:
                await message.answer(f"ℹ️ No hay posiciones abiertas en el exchange.")
                return

            def get_source_tag(symbol):
                sym = str(symbol).strip().upper()
                if sym == 'SOLUSDT': return "B1"
                if sym in ['DOTUSDT', 'AVAXUSDT']: return "B2"
                if self.orchestrator.b1.position_manager and symbol in self.orchestrator.b1.position_manager.active_positions: return "B1"
                if self.orchestrator.b2.position_manager and self.orchestrator.b2.position_manager.has_position(symbol): return "B2"
                if symbol in self.orchestrator.b3.CONFIG['symbols']: return "B3"
                return "Unknown"

            closed_count = 0
            for p in positions:
                sym = p['symbol']
                tag = get_source_tag(sym)
                
                if tag == target_bot:
                    qty = p['quantity']
                    side = p['side']
                    close_side = 'SELL' if side == 'LONG' else 'BUY'
                    
                    await message.answer(f"🛠 Procesando cierre para {sym} ({target_bot})...")
                    
                    # 1. Cancel open orders (SL/TP)
                    try:
                        self.orchestrator.connector.client.futures_cancel_all_open_orders(symbol=sym)
                        logger.info(f"Órdenes canceladas para {sym}")
                    except Exception as e:
                        logger.error(f"Error cancelando órdenes de {sym}: {e}")
                    
                    # 2. Add market close order
                    try:
                        self.orchestrator.connector.client.futures_create_order(
                            symbol=sym,
                            side=close_side,
                            positionSide=side,
                            type='MARKET',
                            quantity=qty
                        )
                        await message.answer(f"✅ Posición cerrada con éxito: {sym} ({side})")
                        closed_count += 1
                        
                        # Note: Local state in PositionManagers might need a tick to realize the position is gone,
                        # but next logic cycle will clean it or webhook will process it.
                    except Exception as e:
                        await message.answer(f"❌ Error al ejecutar MARKET Close en {sym}: {e}")
            
            if closed_count == 0:
                await message.answer(f"🔍 No se encontraron posiciones activas atribuidas a {target_bot}.")
        except Exception as e:
            await message.answer(f"❌ Error crítico procesando cierre de {target_bot}: {e}")
            logger.error(f"Exception in _close_by_bot: {e}")

    # ═══════════════════════════════════════════════════
    #  COMANDO /tendencia — Análisis Bull/Bear Macro
    # ═══════════════════════════════════════════════════

    async def cmd_tendencia(self, message: types.Message):
        """Analiza BTC y ETH con 4 indicadores para determinar bull/bear."""
        try:
            await message.answer("🔍 Analizando tendencia macro (BTC + ETH)...")
            
            connector = self.orchestrator.connector
            symbols = ['BTCUSDT', 'ETHUSDT']
            results = []
            
            for symbol in symbols:
                try:
                    # Obtener 300 velas 4H (suficiente para EMA200)
                    klines = connector.client.futures_klines(
                        symbol=symbol, interval='4h', limit=300
                    )
                    if not klines or len(klines) < 210:
                        results.append({'symbol': symbol, 'error': 'Datos insuficientes'})
                        continue
                    
                    closes = [float(k[4]) for k in klines]
                    highs  = [float(k[2]) for k in klines]
                    lows   = [float(k[3]) for k in klines]
                    price  = closes[-1]
                    
                    # 1. EMA 200 (Precio vs EMA200)
                    ema200 = self._calc_ema(closes, 200)
                    ema200_bull = price > ema200
                    ema200_dist = abs(price - ema200) / ema200 * 100
                    
                    # 2. EMA 50/200 Cross
                    ema50 = self._calc_ema(closes, 50)
                    prev_ema50 = self._calc_ema(closes[:-1], 50)
                    prev_ema200 = self._calc_ema(closes[:-1], 200)
                    cross_bull = ema50 > ema200  # EMA50 está arriba
                    
                    # 3. ADX (14) — fuerza de tendencia
                    adx_val, di_plus, di_minus = self._calc_adx(highs, lows, closes, 14)
                    adx_bull = di_plus > di_minus
                    has_trend = adx_val > 25
                    
                    # 4. RSI (14)
                    rsi = self._calc_rsi(closes, 14)
                    rsi_bull = rsi > 50
                    
                    # ═══ SCORING ═══
                    # Cada indicador tiene peso. Total = 100%
                    # EMA200: 30%, Cross EMA50/200: 25%, ADX: 25%, RSI: 20%
                    bull_score = 0.0
                    details = []
                    
                    # EMA200 (30%)
                    if ema200_bull:
                        bull_score += 30
                        details.append(f"✅ Precio > EMA200 (+{ema200_dist:.1f}%)")
                    else:
                        details.append(f"❌ Precio < EMA200 (-{ema200_dist:.1f}%)")
                    
                    # Cross (25%)
                    if cross_bull:
                        bull_score += 25
                        details.append("✅ EMA50 > EMA200 (Golden)")
                    else:
                        details.append("❌ EMA50 < EMA200 (Death)")
                    
                    # ADX (25%)
                    if has_trend:
                        if adx_bull:
                            bull_score += 25
                            details.append(f"✅ ADX={adx_val:.0f} DI+>DI- (Trend↑)")
                        else:
                            details.append(f"❌ ADX={adx_val:.0f} DI->DI+ (Trend↓)")
                    else:
                        bull_score += 12.5  # Neutral cuando no hay tendencia clara
                        details.append(f"⚠️ ADX={adx_val:.0f} (Sin tendencia clara)")
                    
                    # RSI (20%)
                    if rsi_bull:
                        bull_score += 20
                        details.append(f"✅ RSI={rsi:.0f} > 50 (Momentum↑)")
                    else:
                        details.append(f"❌ RSI={rsi:.0f} < 50 (Momentum↓)")
                    
                    regime = "BULL 🟢" if bull_score >= 50 else "BEAR 🔴"
                    confidence = bull_score if bull_score >= 50 else (100 - bull_score)
                    
                    results.append({
                        'symbol': symbol,
                        'regime': regime,
                        'confidence': confidence,
                        'bull_score': bull_score,
                        'price': price,
                        'ema200': ema200,
                        'adx': adx_val,
                        'rsi': rsi,
                        'details': details,
                    })
                except Exception as e:
                    results.append({'symbol': symbol, 'error': str(e)})
            
            # ═══ FORMATEAR RESPUESTA ═══
            msg = "📊 *ANÁLISIS DE TENDENCIA MACRO*\n"
            msg += f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC\n"
            msg += "━━━━━━━━━━━━━━━━━━━━\n\n"
            
            overall_bull = 0
            valid_count = 0
            
            for r in results:
                if 'error' in r:
                    msg += f"⚠️ *{r['symbol']}*: Error — {r['error']}\n\n"
                    continue
                
                valid_count += 1
                overall_bull += r['bull_score']
                
                msg += f"*{r['symbol']}* — {r['regime']} ({r['confidence']:.0f}%)\n"
                msg += f"💲 Precio: ${r['price']:,.2f}\n"
                for d in r['details']:
                    msg += f"  {d}\n"
                msg += "\n"
            
            # ═══ RESULTADO GLOBAL ═══
            if valid_count > 0:
                avg_bull = overall_bull / valid_count
                global_regime = "BULL 🟢" if avg_bull >= 50 else "BEAR 🔴"
                global_conf = avg_bull if avg_bull >= 50 else (100 - avg_bull)
                
                msg += "━━━━━━━━━━━━━━━━━━━━\n"
                msg += f"🌐 *MERCADO GLOBAL: {global_regime} {global_conf:.0f}%*\n"
                msg += f"📈 Indicadores Bull: {avg_bull:.0f}/100\n"
                
                if avg_bull >= 75:
                    msg += "💡 _Tendencia alcista fuerte. Estrategias LONG favorecidas._"
                elif avg_bull >= 50:
                    msg += "💡 _Tendencia alcista moderada. Operar con cautela._"
                elif avg_bull >= 25:
                    msg += "💡 _Tendencia bajista moderada. Estrategias SHORT favorecidas._"
                else:
                    msg += "💡 _Tendencia bajista fuerte. Máxima precaución con LONGs._"
            
            await message.answer(msg, parse_mode="Markdown")
            
        except Exception as e:
            await message.answer(f"❌ Error en análisis de tendencia: {e}")
            logger.error(f"Error in cmd_tendencia: {e}")

    # ─── Helper: EMA ───
    def _calc_ema(self, data, period):
        if len(data) < period:
            return data[-1]
        k = 2 / (period + 1)
        ema = sum(data[:period]) / period
        for val in data[period:]:
            ema = val * k + ema * (1 - k)
        return ema

    # ─── Helper: RSI ───
    def _calc_rsi(self, closes, period=14):
        if len(closes) < period + 1:
            return 50
        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    # ─── Helper: ADX ───
    def _calc_adx(self, highs, lows, closes, period=14):
        n = len(closes)
        if n < period * 2:
            return 20, 50, 50  # neutral defaults
        
        tr_list = []
        plus_dm = []
        minus_dm = []
        
        for i in range(1, n):
            h = highs[i] - highs[i-1]
            l = lows[i-1] - lows[i]
            plus_dm.append(h if h > l and h > 0 else 0)
            minus_dm.append(l if l > h and l > 0 else 0)
            tr_list.append(max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            ))
        
        # Smoothed
        atr = sum(tr_list[:period]) / period
        sdm_plus = sum(plus_dm[:period]) / period
        sdm_minus = sum(minus_dm[:period]) / period
        
        di_plus_list = []
        di_minus_list = []
        dx_list = []
        
        for i in range(period, len(tr_list)):
            atr = (atr * (period - 1) + tr_list[i]) / period
            sdm_plus = (sdm_plus * (period - 1) + plus_dm[i]) / period
            sdm_minus = (sdm_minus * (period - 1) + minus_dm[i]) / period
            
            di_p = (sdm_plus / atr * 100) if atr > 0 else 0
            di_m = (sdm_minus / atr * 100) if atr > 0 else 0
            di_plus_list.append(di_p)
            di_minus_list.append(di_m)
            
            di_sum = di_p + di_m
            dx = abs(di_p - di_m) / di_sum * 100 if di_sum > 0 else 0
            dx_list.append(dx)
        
        if len(dx_list) < period:
            return 20, 50, 50
        
        adx = sum(dx_list[:period]) / period
        for i in range(period, len(dx_list)):
            adx = (adx * (period - 1) + dx_list[i]) / period
        
        return adx, di_plus_list[-1] if di_plus_list else 50, di_minus_list[-1] if di_minus_list else 50

