"""
ANTIGRAVITY — Webhook Server (Fire-and-Forget)
================================================
Recibe alertas de TradingView y responde HTTP 200 en <100ms.
La ejecución en Binance y notificación a Telegram se procesan
en background via asyncio.create_task().

Patrón: Validate → Respond → Execute (async)
"""

import asyncio
import logging
import os
import time
from aiohttp import web

logger = logging.getLogger('WEBHOOK')


class WebhookServer:
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.app = web.Application()
        self.app.add_routes([
            web.post('/webhook', self.handle_webhook),
            web.post('/webhook/{engine_id}', self.handle_webhook),
            web.get('/', self.handle_health)
        ])
        self.runner = None
        self.site = None

        # Secret Key (Must match TradingView alert message)
        self.secret = os.getenv('WEBHOOK_SECRET', 'ANTIGRAVITY_KEY')

        # Observability counters
        self._received_count = 0
        self._success_count = 0
        self._error_count = 0
        self._last_error = None

    # ═══════════════════════════════════════════════════
    #  ROUTING (< 100ms response)
    # ═══════════════════════════════════════════════════

    async def handle_health(self, request):
        data = {
            "status": "running",
            "webhooks_received": self._received_count,
            "webhooks_success": self._success_count,
            "webhooks_errors": self._error_count
        }
        if self._last_error:
            data["last_error"] = self._last_error
        return web.json_response(data)

    async def handle_webhook(self, request):
        """
        FAST PATH: Validate → Parse → Respond 200 → Fire background task.
        Target: < 100ms total response time.
        """
        t_start = time.monotonic()

        try:
            data = await request.json()
        except Exception:
            return web.Response(status=400, text="Invalid JSON")

        # ─── Security Check ───
        if data.get('pass') != self.secret and data.get('secret') != self.secret:
            logger.warning(f"⛔ Unauthorized Webhook: {request.remote}")
            return web.Response(status=401, text="Unauthorized")

        # ─── Parse Signal ───
        engine_id = data.get('engine', '').upper()
        symbol = data.get('symbol', '').upper()
        side = data.get('side', '').upper()
        price = data.get('price')

        if not engine_id or not symbol or not side:
            return web.Response(status=400, text="Missing: engine, symbol, or side")

        if engine_id not in ('B1', 'B2', 'B3'):
            return web.Response(status=400, text=f"Unknown engine: {engine_id}")

        # ─── Build Signal ───
        signal = {
            'symbol': symbol,
            'side': side,
            'price': price,
            'source': 'tradingview',
            'engine': engine_id
        }

        self._received_count += 1
        t_elapsed_ms = (time.monotonic() - t_start) * 1000

        logger.info(
            f"📨 Webhook #{self._received_count}: {engine_id} {side} {symbol} "
            f"(validated in {t_elapsed_ms:.1f}ms)"
        )

        # ─── FIRE AND FORGET ───
        asyncio.create_task(
            self._process_signal_background(signal, self._received_count)
        )

        # Respond immediately — TradingView gets 200 OK
        return web.json_response({
            "status": "received",
            "webhook_id": self._received_count,
            "engine": engine_id,
            "symbol": symbol,
            "side": side,
            "latency_ms": round(t_elapsed_ms, 1)
        })

    # ═══════════════════════════════════════════════════
    #  BACKGROUND EXECUTION (fire-and-forget)
    # ═══════════════════════════════════════════════════

    async def _process_signal_background(self, signal: dict, webhook_id: int):
        """
        Executes engine signal + Telegram notification in background.
        Completely decoupled from the HTTP response cycle.
        """
        engine_id = signal['engine']
        symbol = signal['symbol']
        side = signal['side']
        t_start = time.monotonic()

        try:
            # ─── Route to Engine ───
            engine = self._get_engine(engine_id)
            if engine is None:
                raise ValueError(f"Engine {engine_id} not available")

            if not hasattr(engine, 'process_external_signal'):
                raise NotImplementedError(
                    f"{engine_id} does not support external signals"
                )

            # Execute (this calls Binance API — may be slow)
            await engine.process_external_signal(signal)

            t_elapsed = time.monotonic() - t_start
            self._success_count += 1

            logger.info(
                f"✅ Webhook #{webhook_id} executed: {engine_id} {side} {symbol} "
                f"({t_elapsed:.2f}s)"
            )

            # ─── Telegram: Success Notification ───
            await self._notify_telegram(
                f"✅ *Webhook #{webhook_id} Ejecutado*\n"
                f"Motor: `{engine_id}` | {side} `{symbol}`\n"
                f"Latencia: `{t_elapsed:.2f}s`"
            )

        except Exception as e:
            t_elapsed = time.monotonic() - t_start
            self._error_count += 1
            self._last_error = f"{engine_id} {side} {symbol}: {str(e)[:300]}"

            logger.error(
                f"❌ Webhook #{webhook_id} FAILED: {engine_id} {side} {symbol} "
                f"— {e} ({t_elapsed:.2f}s)"
            )

            # ─── Telegram: Error Notification (always, even if Binance failed) ───
            await self._notify_telegram(
                f"❌ *Webhook #{webhook_id} ERROR*\n"
                f"Motor: `{engine_id}` | {side} `{symbol}`\n"
                f"Error: `{str(e)[:200]}`\n"
                f"Latencia: `{t_elapsed:.2f}s`"
            )

    # ═══════════════════════════════════════════════════
    #  HELPERS
    # ═══════════════════════════════════════════════════

    def _get_engine(self, engine_id: str):
        """Maps engine ID to orchestrator engine instance."""
        engines = {
            'B1': getattr(self.orchestrator, 'b1', None),
            'B2': getattr(self.orchestrator, 'b2', None),
            'B3': getattr(self.orchestrator, 'b3', None),
        }
        return engines.get(engine_id)

    async def _notify_telegram(self, message: str):
        """
        Decoupled Telegram notification.
        Never raises — errors are logged silently.
        """
        try:
            if hasattr(self.orchestrator, 'telegram') and self.orchestrator.telegram:
                await self.orchestrator.telegram.send_alert(message)
        except Exception as tg_err:
            logger.warning(f"⚠️ Telegram notification failed: {tg_err}")

    # ═══════════════════════════════════════════════════
    #  SERVER LIFECYCLE
    # ═══════════════════════════════════════════════════

    async def start(self, port=8080):
        """Start the web server non-blocking."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, '0.0.0.0', port)
        await self.site.start()
        logger.info(f"🌍 Webhook Server listening on port {port} (Fire-and-Forget mode)")

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()
