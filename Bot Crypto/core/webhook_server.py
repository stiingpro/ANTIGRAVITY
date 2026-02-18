
import logging
import os
from aiohttp import web
from typing import Callable, Awaitable

logger = logging.getLogger('WEBHOOK')

class WebhookServer:
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.app = web.Application()
        self.app.add_routes([
            web.post('/webhook', self.handle_webhook),
            web.get('/', self.handle_health)
        ])
        self.runner = None
        self.site = None
        
        # Secret Key (Must match TradingView alert message)
        self.secret = os.getenv('WEBHOOK_SECRET', 'ANTIGRAVITY_KEY') 

    async def handle_health(self, request):
        return web.Response(text="Antigravity Webhook is Running 🚀")

    async def handle_webhook(self, request):
        try:
            data = await request.json()
            
            # 1. Security Check
            if data.get('pass') != self.secret and data.get('secret') != self.secret:
                logger.warning(f"⛔ Unauthorized Webhook Attempt: {request.remote}")
                return web.Response(status=401, text="Unauthorized")

            # 2. Extract Data
            engine_id = data.get('engine', '').upper() # B1, B2, B3
            symbol = data.get('symbol', '').upper()
            side = data.get('side', '').upper() # BUY, SELL
            # Optional specific params
            price = data.get('price')
            
            logger.info(f"📨 Webhook Received: {engine_id} {side} {symbol}")

            # 3. Route to Engine
            formatted_signal = {
                'symbol': symbol,
                'side': side,
                'price': price,
                'source': 'tradingview'
            }

            if engine_id == 'B1':
                if hasattr(self.orchestrator.b1, 'process_external_signal'):
                    await self.orchestrator.b1.process_external_signal(formatted_signal)
                else:
                    return web.Response(status=501, text="B1 does not support external signals yet")
            
            elif engine_id == 'B2':
                if hasattr(self.orchestrator.b2, 'process_external_signal'):
                    await self.orchestrator.b2.process_external_signal(formatted_signal)
                else:
                    return web.Response(status=501, text="B2 does not support external signals yet")

            elif engine_id == 'B3':
                if hasattr(self.orchestrator.b3, 'process_external_signal'):
                    await self.orchestrator.b3.process_external_signal(formatted_signal)
                else:
                    return web.Response(status=501, text="B3 does not support external signals yet")
            
            else:
                return web.Response(status=400, text=f"Unknown Engine: {engine_id}")

            return web.Response(text="Signal Processed 🚀")

        except Exception as e:
            logger.error(f"❌ Webhook Error: {e}")
            return web.Response(status=500, text=str(e))

    async def start(self, port=8080):
        """Start the web server non-blocking."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, '0.0.0.0', port)
        await self.site.start()
        logger.info(f"🌍 Webhook Server listening on port {port}")

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()
