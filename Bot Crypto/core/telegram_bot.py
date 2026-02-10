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
        self.orchestrator = orchestrator # Referencia al main para callbacks
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
        self.dp.message(Command("status"))(self.cmd_status)
        self.dp.message(Command("kill"))(self.cmd_kill)
        self.dp.message(Command("logs"))(self.cmd_logs)

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

    async def cmd_status(self, message: types.Message):
        """Responde con el estado de los motores."""
        status_report = self.orchestrator.get_status_report()
        await message.answer(status_report, parse_mode="Markdown")

    async def cmd_kill(self, message: types.Message):
        """PANIC BUTTON: Detiene todo."""
        await message.answer("🛑 **KILL SWITCH ACTIVADO** 🛑\nDeteniendo motores y cancelando órdenes...")
        await self.orchestrator.emergency_stop()

    async def cmd_logs(self, message: types.Message):
        """Envía últimos logs (simulado)."""
        # En producción real, leeríamos el archivo.
        await message.answer("📋 Logs: (Funcionalidad pendiente de implementar lectura de archivo)")
