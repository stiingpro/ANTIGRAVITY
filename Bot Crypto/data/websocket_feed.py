"""
WebSocket Feed - Real-time Market Data
=======================================
Conexión WebSocket a Binance Futures para datos en vivo.
Soporta Testnet y Production.
"""

import json
import logging
import asyncio
import time
from typing import Callable, Dict, Optional, List
from datetime import datetime
from threading import Thread

logger = logging.getLogger('WebSocketFeed')


class BinanceWebSocketFeed:
    """
    Feed de datos en tiempo real via WebSocket.
    
    Streams disponibles:
    - Ticker (precio en tiempo real)
    - Klines (velas en streaming)
    - Book Ticker (mejor bid/ask)
    - User Data (órdenes, posiciones)
    """
    
    # URLs de WebSocket
    WS_URLS = {
        'testnet': 'wss://stream.binancefuture.com',
        'production': 'wss://fstream.binance.com'
    }
    
    def __init__(
        self,
        environment: str = 'testnet',
        symbols: List[str] = None,
        timeframe: str = '5m'
    ):
        self.environment = environment
        self.symbols = symbols or ['BTCUSDT']
        self.timeframe = timeframe
        self.ws_url = self.WS_URLS[environment]
        
        # Estado
        self.running = False
        self.ws = None
        self._thread: Optional[Thread] = None
        
        # Callbacks
        self._on_ticker: Optional[Callable] = None
        self._on_kline: Optional[Callable] = None
        self._on_book: Optional[Callable] = None
        
        # Cache de último dato
        self.last_ticker: Dict[str, Dict] = {}
        self.last_kline: Dict[str, Dict] = {}
        
        # Métricas
        self.messages_received = 0
        self.last_message_time: Optional[datetime] = None
        self.reconnect_count = 0
        
        logger.info(f"📡 WebSocket Feed inicializado ({environment})")
        logger.info(f"   Symbols: {', '.join(self.symbols)}")
        logger.info(f"   Timeframe: {timeframe}")
    
    def on_ticker(self, callback: Callable):
        """Registrar callback para actualizaciones de precio."""
        self._on_ticker = callback
    
    def on_kline(self, callback: Callable):
        """Registrar callback para nuevas velas."""
        self._on_kline = callback
    
    def on_book(self, callback: Callable):
        """Registrar callback para book ticker."""
        self._on_book = callback
    
    async def start(self):
        """Iniciar conexión WebSocket."""
        try:
            import websockets
        except ImportError:
            logger.error("❌ Librería 'websockets' no instalada")
            logger.error("   Ejecutar: pip install websockets")
            return False
        
        self.running = True
        
        # Construir streams
        streams = self._build_streams()
        ws_url = f"{self.ws_url}/stream?streams={'/'.join(streams)}"
        
        logger.info(f"🔌 Conectando a WebSocket...")
        logger.info(f"   URL: {self.ws_url}")
        logger.info(f"   Streams: {len(streams)}")
        
        while self.running:
            try:
                async with websockets.connect(
                    ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5
                ) as ws:
                    self.ws = ws
                    logger.info("✅ WebSocket conectado")
                    
                    async for message in ws:
                        if not self.running:
                            break
                        
                        await self._process_message(message)
                        
            except Exception as e:
                if self.running:
                    self.reconnect_count += 1
                    wait = min(30, 2 ** self.reconnect_count)
                    logger.warning(
                        f"⚠️ WebSocket desconectado: {e}. "
                        f"Reconectando en {wait}s... (intento {self.reconnect_count})"
                    )
                    await asyncio.sleep(wait)
        
        logger.info("🔌 WebSocket cerrado")
    
    def start_background(self):
        """Iniciar WebSocket en un thread separado."""
        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.start())
        
        self._thread = Thread(target=_run, daemon=True)
        self._thread.start()
        logger.info("🔄 WebSocket corriendo en background")
    
    async def stop(self):
        """Detener WebSocket."""
        self.running = False
        if self.ws:
            await self.ws.close()
        logger.info("🛑 WebSocket detenido")
    
    def stop_sync(self):
        """Detener WebSocket (versión síncrona)."""
        self.running = False
        logger.info("🛑 WebSocket detenido")
    
    def _build_streams(self) -> List[str]:
        """Construir lista de streams a suscribirse."""
        streams = []
        
        for symbol in self.symbols:
            s = symbol.lower()
            
            # Mini Ticker (precio, volumen)
            streams.append(f"{s}@miniTicker")
            
            # Klines (velas)
            streams.append(f"{s}@kline_{self.timeframe}")
            
            # Book Ticker (mejor bid/ask)
            streams.append(f"{s}@bookTicker")
        
        return streams
    
    async def _process_message(self, raw_message: str):
        """Procesar mensaje recibido del WebSocket."""
        try:
            message = json.loads(raw_message)
            self.messages_received += 1
            self.last_message_time = datetime.now()
            
            # El formato combinado tiene 'stream' y 'data'
            if 'stream' not in message:
                return
            
            stream = message['stream']
            data = message['data']
            
            if '@miniTicker' in stream:
                await self._handle_ticker(data)
            elif '@kline_' in stream:
                await self._handle_kline(data)
            elif '@bookTicker' in stream:
                await self._handle_book(data)
                
        except json.JSONDecodeError:
            logger.warning("⚠️ Mensaje no válido recibido")
        except Exception as e:
            logger.error(f"Error procesando mensaje: {e}")
    
    async def _handle_ticker(self, data: Dict):
        """Procesar actualización de ticker."""
        ticker = {
            'symbol': data['s'],
            'price': float(data['c']),
            'open': float(data['o']),
            'high': float(data['h']),
            'low': float(data['l']),
            'volume': float(data['v']),
            'quote_volume': float(data['q']),
            'timestamp': datetime.now()
        }
        
        self.last_ticker[ticker['symbol']] = ticker
        
        if self._on_ticker:
            self._on_ticker(ticker)
    
    async def _handle_kline(self, data: Dict):
        """Procesar actualización de kline."""
        k = data['k']
        
        kline = {
            'symbol': k['s'],
            'interval': k['i'],
            'open_time': k['t'],
            'open': float(k['o']),
            'high': float(k['h']),
            'low': float(k['l']),
            'close': float(k['c']),
            'volume': float(k['v']),
            'is_closed': k['x'],  # True cuando la vela se cierra
            'trades': k['n'],
            'timestamp': datetime.now()
        }
        
        self.last_kline[kline['symbol']] = kline
        
        if self._on_kline:
            self._on_kline(kline)
    
    async def _handle_book(self, data: Dict):
        """Procesar actualización de book ticker."""
        book = {
            'symbol': data['s'],
            'best_bid': float(data['b']),
            'best_bid_qty': float(data['B']),
            'best_ask': float(data['a']),
            'best_ask_qty': float(data['A']),
            'spread': float(data['a']) - float(data['b']),
            'timestamp': datetime.now()
        }
        
        if self._on_book:
            self._on_book(book)
    
    def get_price(self, symbol: str = 'BTCUSDT') -> Optional[float]:
        """Obtener último precio del cache."""
        ticker = self.last_ticker.get(symbol)
        if ticker:
            return ticker['price']
        return None
    
    def get_last_kline(self, symbol: str = 'BTCUSDT') -> Optional[Dict]:
        """Obtener última kline del cache."""
        return self.last_kline.get(symbol)
    
    def get_status(self) -> Dict:
        """Obtener estado del feed."""
        return {
            'running': self.running,
            'environment': self.environment,
            'symbols': self.symbols,
            'messages': self.messages_received,
            'reconnects': self.reconnect_count,
            'last_message': self.last_message_time.isoformat() if self.last_message_time else None,
            'prices': {
                sym: t['price'] 
                for sym, t in self.last_ticker.items()
            }
        }
