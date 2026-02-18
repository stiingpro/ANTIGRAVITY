import os
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
        self.token = os.environ.get("TELEGRAM_TOKEN")
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
            "/kill — 🛑 Emergencia: Detener todo",
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
                # Check B1
                if self.orchestrator.b1.position_manager and \
                   symbol in self.orchestrator.b1.position_manager.active_positions:
                    return "🏎 B1"
                
                # Check B2
                if self.orchestrator.b2.position_manager and \
                   self.orchestrator.b2.position_manager.has_position(symbol):
                    return "🛡 B2"
                
                # Heuristic: SOLUSDT is B1 Priority
                if str(symbol).strip().upper() == 'SOLUSDT':
                    return "🏎 B1"
                
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
