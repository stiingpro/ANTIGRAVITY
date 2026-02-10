"""
B1_SPRINT Engine - Demo Test
=============================
Prueba completa del motor B1 en Binance Demo.
Ejecuta: py test_b1_demo.py
"""

import os
import sys
import time
import logging
from datetime import datetime
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('B1_DemoTest')

# Cargar credenciales testnet
env_path = os.path.join(os.path.dirname(__file__), '.env.testnet')
if os.path.exists(env_path):
    load_dotenv(env_path)
    logger.info("✅ Credenciales testnet cargadas")


def test_strategy_indicators():
    """Test 1: Verificar cálculo de indicadores técnicos."""
    print("\n" + "=" * 60)
    print("📊 TEST 1: INDICADORES TÉCNICOS")
    print("=" * 60)
    
    from engines.b1_sprint.strategy import B1Strategy
    from engines.b1_sprint.engine import B1SprintEngine
    
    config = B1SprintEngine.CONFIG
    strategy = B1Strategy(config)
    
    # Simular datos de mercado
    # Crear klines fake para probar indicadores
    fake_klines = []
    base_price = 70000
    
    for i in range(100):
        # Simular tendencia alcista suave
        price = base_price + (i * 50) + ((-1)**i * 100)  
        kline = [
            int(time.time() * 1000),  # Open time
            str(price - 50),           # Open
            str(price + 100),          # High
            str(price - 100),          # Low
            str(price),                # Close
            "100",                     # Volume
            int(time.time() * 1000),  # Close time
            "7000000",                # Quote volume
            100,                       # Trades
            "50",                      # Taker buy base
            "3500000",                # Taker buy quote
            "0"                        # Ignore
        ]
        fake_klines.append(kline)
    
    market_data = {
        'symbol': 'BTCUSDT',
        'price': 75000.0,
        'klines': fake_klines,
        'timestamp': datetime.now()
    }
    
    # Probar indicadores
    context = strategy._calculate_indicators(market_data)
    
    if context:
        print(f"  EMA rápida (9):  ${context.ema_fast:,.2f}")
        print(f"  EMA lenta (21):  ${context.ema_slow:,.2f}")
        print(f"  RSI (14):        {context.rsi:.1f}")
        print(f"  Momentum:        {context.momentum:.4f}")
        print(f"  Tendencia:       {context.trend}")
        print(f"  Volatilidad:     {context.volatility}")
        
        return True, context
    else:
        print("  ❌ Error calculando indicadores")
        return False, None


def test_risk_manager():
    """Test 2: Verificar gestión de riesgo."""
    print("\n" + "=" * 60)
    print("🛡️ TEST 2: RISK MANAGER")
    print("=" * 60)
    
    from engines.b1_sprint.risk_manager import B1RiskManager
    from engines.b1_sprint.engine import B1SprintEngine, TradeSignal, TradeSide
    
    config = B1SprintEngine.CONFIG
    rm = B1RiskManager(config, initial_balance=5000.0)
    
    # Señal fuerte
    strong_signal = TradeSignal(
        symbol='BTCUSDT',
        side=TradeSide.LONG,
        strength=0.8,
        entry_price=70000,
        stop_loss=68600,   # 2% SL
        take_profit=72800,  # 4% TP
        timestamp=datetime.now(),
        reason="Test signal fuerte"
    )
    
    # Señal débil
    weak_signal = TradeSignal(
        symbol='BTCUSDT',
        side=TradeSide.LONG,
        strength=0.2,
        entry_price=70000,
        stop_loss=69500,
        take_profit=70500,
        timestamp=datetime.now(),
        reason="Test signal débil"
    )
    
    # Tests
    approved_strong = rm.approve_trade(strong_signal, 5000.0)
    approved_weak = rm.approve_trade(weak_signal, 5000.0)
    
    print(f"  Señal fuerte (0.8):  {'✅ Aprobada' if approved_strong else '❌ Rechazada'}")
    print(f"  Señal débil (0.2):   {'✅ Aprobada' if approved_weak else '❌ Rechazada'}")
    
    # Position sizing
    size = rm.calculate_position_size(strong_signal, 5000.0)
    value_usd = size * 70000
    print(f"\n  Position Size:  {size} BTC (${value_usd:,.2f} USDT)")
    print(f"  % del capital:  {(value_usd / 5000) * 100:.1f}%")
    
    # Leverage
    leverage = rm.calculate_leverage(strong_signal, 5000.0)
    print(f"  Leverage:       {leverage}x")
    
    # Risk/Reward
    risk = abs(strong_signal.entry_price - strong_signal.stop_loss)
    reward = abs(strong_signal.take_profit - strong_signal.entry_price)
    print(f"\n  Risk:   ${risk:,.0f} ({risk/70000*100:.1f}%)")
    print(f"  Reward: ${reward:,.0f} ({reward/70000*100:.1f}%)")
    print(f"  Ratio:  {reward/risk:.1f}:1")
    
    return approved_strong and not approved_weak


def test_kill_switch():
    """Test 3: Verificar kill switch."""
    print("\n" + "=" * 60)
    print("🚨 TEST 3: KILL SWITCH")
    print("=" * 60)
    
    from safety.kill_switch import KillSwitch
    
    ks = KillSwitch(max_drawdown_pct=15.0, hibernation_hours=24)
    
    # Caso 1: Balance normal (no trigger)
    trigger_normal = ks.check_trigger(
        initial_balance=5000,
        current_balance=4500  # -10% drawdown
    )
    print(f"  Balance $4500 (-10%):  {'🚨 TRIGGER' if trigger_normal else '✅ Safe'}")
    
    # Caso 2: Balance crítico (trigger)
    trigger_critical = ks.check_trigger(
        initial_balance=5000,
        current_balance=4200  # -16% drawdown
    )
    print(f"  Balance $4200 (-16%):  {'🚨 TRIGGER' if trigger_critical else '✅ Safe'}")
    
    # Caso 3: Balance en límite
    trigger_edge = ks.check_trigger(
        initial_balance=5000,
        current_balance=4250  # -15% exacto
    )
    print(f"  Balance $4250 (-15%):  {'🚨 TRIGGER' if trigger_edge else '✅ Safe'}")
    
    # Status
    status = ks.get_status()
    print(f"\n  Estado actual:    {'🔴 Activo' if status['is_active'] else '🟢 Inactivo'}")
    print(f"  Max drawdown:     {status['max_drawdown_pct']}%")
    print(f"  Hibernación:      {status['hibernation_hours']}h")
    
    return not trigger_normal and trigger_critical


def test_live_market_data():
    """Test 4: Obtener datos reales del mercado demo."""
    print("\n" + "=" * 60)
    print("📡 TEST 4: DATOS DE MERCADO EN VIVO (DEMO)")
    print("=" * 60)
    
    try:
        from binance.client import Client
        
        api_key = os.getenv('B1_TESTNET_API_KEY')
        api_secret = os.getenv('B1_TESTNET_API_SECRET')
        
        if not api_key or not api_secret:
            print("  ⚠️ Credenciales testnet no encontradas")
            return False
        
        client = Client(api_key=api_key, api_secret=api_secret, testnet=True)
        client.FUTURES_URL = 'https://testnet.binancefuture.com'
        
        # Obtener precio actual
        ticker = client.futures_symbol_ticker(symbol='BTCUSDT')
        price = float(ticker['price'])
        print(f"  💰 Precio BTC: ${price:,.2f}")
        
        # Obtener klines reales
        klines = client.futures_klines(
            symbol='BTCUSDT',
            interval='5m',
            limit=100
        )
        print(f"  📊 Klines recibidos: {len(klines)} velas (5m)")
        
        if klines:
            last_kline = klines[-1]
            print(f"  📈 Última vela:")
            print(f"     Open:   ${float(last_kline[1]):,.2f}")
            print(f"     High:   ${float(last_kline[2]):,.2f}")
            print(f"     Low:    ${float(last_kline[3]):,.2f}")
            print(f"     Close:  ${float(last_kline[4]):,.2f}")
            print(f"     Volume: {float(last_kline[5]):,.2f}")
        
        # Probar estrategia con datos reales
        from engines.b1_sprint.strategy import B1Strategy
        from engines.b1_sprint.engine import B1SprintEngine
        
        strategy = B1Strategy(B1SprintEngine.CONFIG)
        
        market_data = {
            'symbol': 'BTCUSDT',
            'price': price,
            'klines': klines,
            'timestamp': datetime.now()
        }
        
        context = strategy._calculate_indicators(market_data)
        if context:
            print(f"\n  📊 Análisis en VIVO:")
            print(f"     EMA(9):      ${context.ema_fast:,.2f}")
            print(f"     EMA(21):     ${context.ema_slow:,.2f}")
            print(f"     RSI(14):     {context.rsi:.1f}")
            print(f"     Momentum:    {context.momentum:.4f}")
            print(f"     Tendencia:   {context.trend}")
            print(f"     Volatilidad: {context.volatility}")
        
        # Verificar si hay señal
        signal = strategy.analyze(market_data)
        if signal:
            print(f"\n  📈 ¡SEÑAL DETECTADA!")
            print(f"     Lado:      {signal.side.value}")
            print(f"     Fuerza:    {signal.strength:.2f}")
            print(f"     Entry:     ${signal.entry_price:,.2f}")
            print(f"     SL:        ${signal.stop_loss:,.2f}")
            print(f"     TP:        ${signal.take_profit:,.2f}")
            print(f"     Razón:     {signal.reason}")
        else:
            print(f"\n  ⏸️ Sin señal de trading en este momento")
        
        # Balance
        account = client.futures_account_balance()
        for asset in account:
            if asset['asset'] == 'USDT':
                print(f"\n  💰 Balance Demo: ${float(asset['balance']):,.2f} USDT")
                break
        
        return True
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def test_simulated_trade():
    """Test 5: Simular flujo completo de trading (sin ejecutar orden real)."""
    print("\n" + "=" * 60)
    print("🎯 TEST 5: SIMULACIÓN DE FLUJO COMPLETO")
    print("=" * 60)
    
    from engines.b1_sprint.engine import B1SprintEngine, TradeSignal, TradeSide
    from engines.b1_sprint.strategy import B1Strategy
    from engines.b1_sprint.risk_manager import B1RiskManager
    
    config = B1SprintEngine.CONFIG
    balance = 5000.0
    
    strategy = B1Strategy(config)
    risk = B1RiskManager(config, balance)
    
    # Crear señal simulada
    signal = TradeSignal(
        symbol='BTCUSDT',
        side=TradeSide.LONG,
        strength=0.75,
        entry_price=70000,
        stop_loss=68600,
        take_profit=72800,
        timestamp=datetime.now(),
        reason="Simulación: RSI=35, trend=bullish"
    )
    
    print(f"  📊 Señal: {signal.side.value} BTC @ ${signal.entry_price:,.0f}")
    print(f"  📊 Fuerza: {signal.strength}")
    
    # Risk check
    approved = risk.approve_trade(signal, balance)
    print(f"\n  🛡️ Risk Manager: {'✅ APROBADO' if approved else '❌ RECHAZADO'}")
    
    if approved:
        # Position sizing
        qty = risk.calculate_position_size(signal, balance)
        leverage = risk.calculate_leverage(signal, balance)
        notional = qty * signal.entry_price
        
        margin = notional / leverage
        potential_loss = qty * abs(signal.entry_price - signal.stop_loss)
        potential_profit = qty * abs(signal.take_profit - signal.entry_price)
        
        print(f"\n  📐 Ejecución simulada:")
        print(f"     Cantidad:     {qty} BTC")
        print(f"     Notional:     ${notional:,.2f}")
        print(f"     Leverage:     {leverage}x")
        print(f"     Margen req:   ${margin:,.2f}")
        print(f"     SL:           ${signal.stop_loss:,.0f} (-{abs(signal.entry_price - signal.stop_loss)/signal.entry_price*100:.1f}%)")
        print(f"     TP:           ${signal.take_profit:,.0f} (+{abs(signal.take_profit - signal.entry_price)/signal.entry_price*100:.1f}%)")
        print(f"     Pérdida max:  ${potential_loss:,.2f}")
        print(f"     Ganancia pot: ${potential_profit:,.2f}")
        print(f"     R/R:          {potential_profit/potential_loss:.1f}:1")
        
        return True
    
    return False


def main():
    """Ejecutar todos los tests."""
    print("=" * 60)
    print("🚀 ANTIGRAVITY HIGH - B1_SPRINT ENGINE TEST")
    print(f"   Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Entorno: Demo/Testnet")
    print("=" * 60)
    
    results = {}
    
    # Test 1: Indicadores
    passed, _ = test_strategy_indicators()
    results['indicators'] = '✅ PASS' if passed else '❌ FAIL'
    
    # Test 2: Risk Manager
    passed = test_risk_manager()
    results['risk_manager'] = '✅ PASS' if passed else '❌ FAIL'
    
    # Test 3: Kill Switch
    passed = test_kill_switch()
    results['kill_switch'] = '✅ PASS' if passed else '❌ FAIL'
    
    # Test 4: Datos en vivo
    passed = test_live_market_data()
    results['live_data'] = '✅ PASS' if passed else '❌ FAIL'
    
    # Test 5: Simulación
    passed = test_simulated_trade()
    results['simulation'] = '✅ PASS' if passed else '❌ FAIL'
    
    # Resumen
    print("\n" + "=" * 60)
    print("📋 RESULTADOS DEL TEST")
    print("=" * 60)
    
    for test, result in results.items():
        print(f"  {test}: {result}")
    
    all_passed = all('✅' in v for v in results.values())
    
    print("\n" + "=" * 60)
    status = "🎉 ALL TESTS PASSED" if all_passed else "⚠️ SOME TESTS FAILED"
    print(f"ESTADO FINAL: {status}")
    print("=" * 60)
    
    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
