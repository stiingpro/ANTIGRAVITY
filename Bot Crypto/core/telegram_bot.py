import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

logger = logging.getLogger('Core.Telegram')

class TelegramInterface:
    """
    Interfaz de Control y Alertas (Telegram).
    """
    def __init__(self, orchestrator):
        self.token = os.environ.get("TELEGRAM_TOKEN")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        self.orchestrator = orchestrator
        self.bot = None
        self.dp = None
        self.polling_task = None

    async def start(self):
        if not self.token:
            logger.warning("⚠️ Telegram Token no encontrado. Bot DESACTIVADO.")
            return

        self.bot = Bot(token=self.token)
        self.dp = Dispatcher()
        
        # Registrar comandos
        self.dp.message(Command("start"))(self.cmd_start)
        self.dp.message(Command("help"))(self.cmd_help)
        self.dp.message(Command("status"))(self.cmd_status)
        self.dp.message(Command("balance"))(self.cmd_balance)
        self.dp.message(Command("positions"))(self.cmd_positions)
        self.dp.message(Command("kill"))(self.cmd_kill)

        logger.info("🤖 Telegram Bot Iniciado.")
        
        # Start polling
        self.polling_task = asyncio.create_task(self.dp.start_polling(self.bot))
        
        # Notificar inicio
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

    # --- Comandos ---

    async def cmd_start(self, message: types.Message):
        """Mensaje de bienvenida."""
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
        """Lista de comandos disponibles."""
        await message.answer(
            "📋 *COMANDOS DISPONIBLES*\n\n"
            "/status — Estado de los 3 motores\n"
            "/balance — Balance detallado USDT\n"
            "/positions — Posiciones abiertas\n"
            "/kill — 🛑 Detener todo (emergencia)\n"
            "/help — Este menú",
            parse_mode="Markdown"
        )

    async def cmd_status(self, message: types.Message):
        """Responde con el estado de los motores."""
        try:
            status_report = self.orchestrator.get_status_report()
            await message.answer(status_report, parse_mode="Markdown")
        except Exception as e:
            await message.answer(f"❌ Error obteniendo status: {e}")

    async def cmd_balance(self, message: types.Message):
        """Muestra balance detallado."""
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
        """Muestra posiciones abiertas."""
        try:
            positions = self.orchestrator.connector.get_open_positions()
            if not positions:
                await message.answer("📊 No hay posiciones abiertas.")
                return
            
            lines = [f"📊 *POSICIONES ABIERTAS ({len(positions)})*\n"]
            for p in positions:
                emoji = '🟢' if p['pnl'] >= 0 else '🔴'
                lines.append(
                    f"{emoji} *{p['symbol']}* {p['side']}\n"
                    f"   Entry: `${p['entry_price']:.4f}`\n"
                    f"   Qty: `{p['quantity']}`  x{p['leverage']}\n"
                    f"   PnL: `${p['pnl']:.2f}`"
                )
            await message.answer("\n".join(lines), parse_mode="Markdown")
        except Exception as e:
            await message.answer(f"❌ Error: {e}")

    async def cmd_kill(self, message: types.Message):
        """PANIC BUTTON: Detiene todo."""
        await message.answer("🛑 *KILL SWITCH ACTIVADO* 🛑\nDeteniendo motores...", parse_mode="Markdown")
        await self.orchestrator.emergency_stop("Manual Kill via Telegram")

