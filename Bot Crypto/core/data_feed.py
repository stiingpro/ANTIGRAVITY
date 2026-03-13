import asyncio
import json
import logging
import aiohttp
from typing import List, Dict, Callable, Set

logger = logging.getLogger('Core.DataFeed')

class DataFeed:
    """
    Módulo Central de Datos (Singleton-like).
    Mantiene 1 conexión WebSocket a Binance Futures.
    Distribuye eventos de Klines a los suscriptores (Motores).
    """
    def __init__(self, testnet: bool = True):
        self.base_url = "wss://stream.binancefuture.com/ws" if testnet else "wss://fstream.binance.com/ws"
        self.subscribers: List[Callable] = []
        self.symbols: Set[str] = set()
        self.running = False
        self.ws = None

    def subscribe_engine(self, callback: Callable):
        """Registra un motor para recibir actualizaciones."""
        self.subscribers.append(callback)

    def add_symbol(self, symbol: str):
        """Añade un símbolo a la lista de monitoreo."""
        self.symbols.add(symbol.lower())

    async def start(self):
        """Inicia el loop de WebSocket."""
        self.running = True
        streams = [f"{s}@kline_1m" for s in self.symbols] # Base stream, engines aggregate if needed or we subscribe to multiple
        # Para optimizar, nos suscribiremos a kline_1m y dejaremos que los motores agreguen, 
        # O nos suscribimos a los TFs necesarios: 5m, 1h, 4h.
        # Plan optimizado: Suscribirse directo a los streams necesarios.
        
        # B1: 5m
        # B2: 1h
        # B3: 4h
        
        # Generar streams combinados
        combined_streams = []
        for s in self.symbols:
            combined_streams.append(f"{s}@kline_5m")
            combined_streams.append(f"{s}@kline_1h")
            combined_streams.append(f"{s}@kline_4h")
            
        stream_url = f"{self.base_url}/{'/'.join(combined_streams)}"
        logger.info(f"📡 Conectando a WS: {len(combined_streams)} streams...")
        
        while self.running:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(stream_url) as ws:
                        self.ws = ws
                        logger.info("✅ WebSocket Conectado.")
                        
                        async for msg in ws:
                            if not self.running:
                                break
                            
                            data = json.loads(msg.data)
                            # Data format: {'e': 'kline', 'E': 123, 's': 'BTCUSDT', 'k': {...}}
                            
                            if 'e' in data and data['e'] == 'kline':
                                await self._dispatch(data)
                                
            except Exception as e:
                logger.error(f"❌ WS Error: {e}. Reintentando en 5s...")
                await asyncio.sleep(5)

    LATEST_PRICES: Dict[str, float] = {}

    async def _dispatch(self, data: Dict):
        """Envía datos a todos los motores suscritos."""
        # data['k'] contains candle info
        if 'k' in data and 's' in data:
            DataFeed.LATEST_PRICES[data['s']] = float(data['k']['c'])
            
        for callback in self.subscribers:
            try:
                # Fire and forget / await
                await callback(data)
            except Exception as e:
                logger.error(f"⚠️ Error en callback de motor: {e}")

    async def stop(self):
        self.running = False
        if self.ws:
            await self.ws.close()
