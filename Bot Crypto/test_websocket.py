"""
Test WebSocket Feed + Price Cache
==================================
Conecta al WebSocket de Binance Demo por 15 segundos y valida datos.
"""

import os
import sys
import asyncio
import logging
from datetime import datetime
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('WS_Test')

load_dotenv(os.path.join(os.path.dirname(__file__), '.env.testnet'))


async def test_websocket():
    """Test WebSocket feed con datos en vivo."""
    print("=" * 60)
    print("📡 TEST WEBSOCKET FEED - B1_SPRINT")
    print(f"   Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    results = {}
    
    # === Test 1: Price Cache con datos históricos ===
    print("\n📊 Test 1: Price Cache con datos REST API...")
    
    try:
        from binance.client import Client
        from data.price_cache import PriceCache
        
        api_key = os.getenv('B1_TESTNET_API_KEY')
        api_secret = os.getenv('B1_TESTNET_API_SECRET')
        
        client = Client(api_key=api_key, api_secret=api_secret, testnet=True)
        client.FUTURES_URL = 'https://testnet.binancefuture.com'
        
        # Cargar velas históricas
        klines = client.futures_klines(symbol='BTCUSDT', interval='5m', limit=100)
        
        cache = PriceCache(symbol='BTCUSDT')
        cache.load_historical(klines)
        
        summary = cache.get_summary()
        print(f"  Velas cargadas: {summary['candles']}")
        print(f"  Precio:         ${summary['price']:,.2f}")
        print(f"  EMA(9):         ${summary['ema_9']:,.2f}")
        print(f"  EMA(21):        ${summary['ema_21']:,.2f}")
        print(f"  RSI(14):        {summary['rsi']}")
        print(f"  MACD:           {summary['macd']:.2f}")
        print(f"  MACD Signal:    {summary['macd_signal']:.2f}")
        print(f"  ATR(14):        ${summary['atr']:,.2f}")
        print(f"  Tendencia:      {summary['trend']}")
        print(f"  Volatilidad:    {summary['volatility']}")
        print(f"  Momentum:       {summary['momentum']:.4f}")
        
        results['price_cache'] = '✅ PASS'
    except Exception as e:
        print(f"  ❌ Error: {e}")
        results['price_cache'] = f'❌ FAIL: {e}'
    
    # === Test 2: WebSocket Connection ===
    print(f"\n📡 Test 2: WebSocket Feed (15 segundos)...")
    
    try:
        from data.websocket_feed import BinanceWebSocketFeed
        
        feed = BinanceWebSocketFeed(
            environment='testnet',
            symbols=['BTCUSDT'],
            timeframe='5m'
        )
        
        # Contadores
        ticker_count = 0
        kline_count = 0
        prices_seen = []
        
        def on_ticker(data):
            nonlocal ticker_count
            ticker_count += 1
            prices_seen.append(data['price'])
            if ticker_count <= 3 or ticker_count % 10 == 0:
                print(f"  📈 Ticker #{ticker_count}: ${data['price']:,.2f} "
                      f"(vol: {data['volume']:,.0f})")
        
        def on_kline(data):
            nonlocal kline_count
            kline_count += 1
            status = "🔒 CERRADA" if data['is_closed'] else "🔓 abierta"
            if kline_count <= 3:
                print(f"  📊 Kline #{kline_count}: O={data['open']:,.2f} "
                      f"H={data['high']:,.2f} L={data['low']:,.2f} "
                      f"C={data['close']:,.2f} [{status}]")
        
        feed.on_ticker(on_ticker)
        feed.on_kline(on_kline)
        
        # Correr WebSocket por 15 segundos
        async def run_timed():
            task = asyncio.create_task(feed.start())
            await asyncio.sleep(15)
            feed.running = False
            try:
                await asyncio.wait_for(task, timeout=3)
            except (asyncio.TimeoutError, Exception):
                pass
        
        await run_timed()
        
        # Resultados
        status = feed.get_status()
        print(f"\n  📊 Resumen WebSocket:")
        print(f"     Mensajes recibidos:  {status['messages']}")
        print(f"     Tickers:            {ticker_count}")
        print(f"     Klines:             {kline_count}")
        print(f"     Reconexiones:       {status['reconnects']}")
        
        if prices_seen:
            print(f"     Precio min:         ${min(prices_seen):,.2f}")
            print(f"     Precio max:         ${max(prices_seen):,.2f}")
            print(f"     Spread:             ${max(prices_seen) - min(prices_seen):,.2f}")
        
        if ticker_count > 0:
            results['websocket'] = f'✅ PASS ({ticker_count} tickers, {kline_count} klines)'
        else:
            results['websocket'] = '❌ FAIL: No se recibieron datos'
            
    except Exception as e:
        print(f"  ❌ Error: {e}")
        results['websocket'] = f'❌ FAIL: {e}'
    
    # === Test 3: Integración Cache + WebSocket ===
    print(f"\n🔗 Test 3: Integración Price Cache + Estrategia...")
    
    try:
        from engines.b1_sprint.strategy import B1Strategy
        from engines.b1_sprint.engine import B1SprintEngine
        
        # Usar market_data del cache
        market_data = cache.get_market_data()
        
        strategy = B1Strategy(B1SprintEngine.CONFIG)
        signal = strategy.analyze(market_data)
        
        ind = cache.indicators
        print(f"  📊 Indicadores del cache:")
        print(f"     EMA(9):    ${ind.ema_9:,.2f}")
        print(f"     EMA(21):   ${ind.ema_21:,.2f}")
        print(f"     RSI:       {ind.rsi_14:.1f}")
        print(f"     MACD:      {ind.macd_line:.2f} (Signal: {ind.macd_signal:.2f})")
        print(f"     ATR:       ${ind.atr_14:,.2f}")
        print(f"     Trend:     {ind.trend}")
        
        if signal:
            print(f"\n  📈 Señal generada: {signal.side.value} @ ${signal.entry_price:,.2f}")
        else:
            print(f"\n  ⏸️ Sin señal (mercado neutral)")
        
        results['integration'] = '✅ PASS'
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        results['integration'] = f'❌ FAIL: {e}'
    
    # === Resumen ===
    print("\n" + "=" * 60)
    print("📋 RESULTADOS")
    print("=" * 60)
    
    for test, result in results.items():
        print(f"  {test}: {result}")
    
    all_passed = all('✅' in str(v) for v in results.values())
    status = "🎉 ALL TESTS PASSED" if all_passed else "⚠️ SOME TESTS FAILED"
    
    print(f"\n{'=' * 60}")
    print(f"ESTADO FINAL: {status}")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    asyncio.run(test_websocket())
