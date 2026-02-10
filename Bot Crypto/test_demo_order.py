"""
============================================
ANTIGRAVITY HIGH - PRUEBA DE ÓRDENES DEMO
============================================
Script de prueba para verificar ejecución de órdenes
en el Demo Trading de Binance (dinero ficticio).

Motor: B1_SPRINT
Símbolo: BTCUSDT
Operación: Long pequeño → cerrar → verificar

⚠️ ESTE SCRIPT USA DINERO FICTICIO DEL DEMO
============================================
"""

import os
import time
import logging
from datetime import datetime
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('DemoOrderTest')


class DemoOrderTester:
    """Prueba de ejecución de órdenes en Demo Binance."""
    
    def __init__(self, motor: str = 'B1'):
        self.motor = motor
        self.client = None
        self.connected = False
        
        # Cargar credenciales del Testnet
        env_path = os.path.join(os.path.dirname(__file__), '.env.testnet')
        if os.path.exists(env_path):
            load_dotenv(env_path)
            logger.info(f"✅ Cargado: .env.testnet")
        
        # Obtener credenciales
        self.api_key = os.getenv(f'{motor}_TESTNET_API_KEY')
        self.api_secret = os.getenv(f'{motor}_TESTNET_API_SECRET')
        
        if not self.api_key or not self.api_secret:
            raise ValueError(f"❌ Credenciales no encontradas para {motor}_TESTNET")
    
    def connect(self) -> bool:
        """Conectar a Binance Demo/Testnet."""
        try:
            from binance.client import Client
            
            self.client = Client(
                api_key=self.api_key,
                api_secret=self.api_secret,
                testnet=True
            )
            
            # Configurar URL del testnet
            self.client.FUTURES_URL = 'https://testnet.binancefuture.com'
            
            # Verificar conexión
            server_time = self.client.futures_time()
            self.connected = True
            
            logger.info(f"✅ Conectado a Binance Demo")
            logger.info(f"   Server time: {datetime.fromtimestamp(server_time['serverTime']/1000)}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error de conexión: {str(e)}")
            return False
    
    def get_balance(self) -> float:
        """Obtener balance USDT disponible."""
        try:
            account = self.client.futures_account()
            for asset in account['assets']:
                if asset['asset'] == 'USDT':
                    available = float(asset['availableBalance'])
                    logger.info(f"💰 Balance disponible: ${available:.2f} USDT")
                    return available
            return 0.0
        except Exception as e:
            logger.error(f"❌ Error al obtener balance: {str(e)}")
            return 0.0
    
    def get_btc_price(self) -> float:
        """Obtener precio actual de BTC."""
        try:
            ticker = self.client.futures_symbol_ticker(symbol='BTCUSDT')
            price = float(ticker['price'])
            logger.info(f"📊 Precio BTC: ${price:,.2f}")
            return price
        except Exception as e:
            logger.error(f"❌ Error al obtener precio: {str(e)}")
            return 0.0
    
    def place_market_order(self, side: str, quantity: float) -> dict:
        """
        Colocar orden de mercado.
        
        Args:
            side: 'BUY' o 'SELL'
            quantity: Cantidad en BTC
        """
        try:
            order = self.client.futures_create_order(
                symbol='BTCUSDT',
                side=side,
                type='MARKET',
                quantity=quantity
            )
            
            logger.info(f"✅ Orden {side} ejecutada:")
            logger.info(f"   Order ID: {order['orderId']}")
            logger.info(f"   Symbol: {order['symbol']}")
            logger.info(f"   Quantity: {order['origQty']}")
            logger.info(f"   Status: {order['status']}")
            
            return order
            
        except Exception as e:
            logger.error(f"❌ Error al crear orden: {str(e)}")
            return {'error': str(e)}
    
    def get_open_positions(self) -> list:
        """Obtener posiciones abiertas."""
        try:
            positions = self.client.futures_position_information(symbol='BTCUSDT')
            open_positions = [
                p for p in positions 
                if float(p['positionAmt']) != 0
            ]
            return open_positions
        except Exception as e:
            logger.error(f"❌ Error al obtener posiciones: {str(e)}")
            return []
    
    def close_all_positions(self) -> bool:
        """Cerrar todas las posiciones en BTCUSDT."""
        try:
            positions = self.get_open_positions()
            
            if not positions:
                logger.info("📊 No hay posiciones abiertas para cerrar")
                return True
            
            for pos in positions:
                amount = float(pos['positionAmt'])
                if amount > 0:
                    # Posición LONG - cerrar con SELL
                    self.place_market_order('SELL', abs(amount))
                elif amount < 0:
                    # Posición SHORT - cerrar con BUY
                    self.place_market_order('BUY', abs(amount))
            
            logger.info("✅ Todas las posiciones cerradas")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error al cerrar posiciones: {str(e)}")
            return False
    
    def run_full_test(self) -> dict:
        """
        Ejecutar prueba completa de trading:
        1. Conectar
        2. Verificar balance
        3. Abrir posición LONG
        4. Esperar 5 segundos
        5. Cerrar posición
        6. Verificar resultado
        """
        print("\n" + "=" * 60)
        print("🧪 PRUEBA DE EJECUCIÓN DE ÓRDENES - DEMO")
        print("=" * 60)
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'motor': self.motor,
            'tests': {}
        }
        
        # Test 1: Conexión
        print("\n📡 Test 1: Conexión...")
        if not self.connect():
            results['tests']['connection'] = '❌ FAIL'
            results['status'] = '❌ FAILED - No se pudo conectar'
            return results
        results['tests']['connection'] = '✅ PASS'
        
        # Test 2: Balance
        print("\n💰 Test 2: Verificar balance...")
        balance_before = self.get_balance()
        if balance_before <= 0:
            results['tests']['balance'] = '❌ FAIL - Sin fondos'
            results['status'] = '❌ FAILED - Sin balance disponible'
            return results
        results['tests']['balance'] = f'✅ PASS (${balance_before:.2f})'
        
        # Test 3: Obtener precio
        print("\n📊 Test 3: Obtener precio BTC...")
        btc_price = self.get_btc_price()
        if btc_price <= 0:
            results['tests']['price'] = '❌ FAIL'
            return results
        results['tests']['price'] = f'✅ PASS (${btc_price:,.2f})'
        
        # Calcular cantidad mínima ($100 notional = ~0.002 BTC a $70k)
        quantity = 0.002
        
        # Test 4: Abrir posición LONG
        print(f"\n📈 Test 4: Abrir LONG {quantity} BTC...")
        order_open = self.place_market_order('BUY', quantity)
        if 'error' in order_open:
            results['tests']['open_long'] = f"❌ FAIL: {order_open['error']}"
        else:
            results['tests']['open_long'] = f"✅ PASS (OrderID: {order_open['orderId']})"
        
        # Esperar 3 segundos
        print("\n⏳ Esperando 3 segundos...")
        time.sleep(3)
        
        # Test 5: Verificar posición abierta
        print("\n🔍 Test 5: Verificar posición...")
        positions = self.get_open_positions()
        if positions:
            pos = positions[0]
            results['tests']['position_open'] = f"✅ PASS ({pos['positionAmt']} BTC)"
            logger.info(f"   Position: {pos['positionAmt']} BTC")
            logger.info(f"   Entry Price: ${float(pos['entryPrice']):,.2f}")
            logger.info(f"   Unrealized PnL: ${float(pos['unRealizedProfit']):.2f}")
        else:
            results['tests']['position_open'] = '⚠️ No se detectó posición'
        
        # Test 6: Cerrar posición
        print(f"\n📉 Test 6: Cerrar posición SELL {quantity} BTC...")
        order_close = self.place_market_order('SELL', quantity)
        if 'error' in order_close:
            results['tests']['close_position'] = f"❌ FAIL: {order_close['error']}"
        else:
            results['tests']['close_position'] = f"✅ PASS (OrderID: {order_close['orderId']})"
        
        # Test 7: Verificar posición cerrada
        print("\n🔍 Test 7: Verificar cierre...")
        time.sleep(2)
        positions_after = self.get_open_positions()
        if not positions_after:
            results['tests']['position_closed'] = '✅ PASS (sin posiciones)'
        else:
            results['tests']['position_closed'] = f'⚠️ Posiciones restantes: {len(positions_after)}'
        
        # Test 8: Balance final
        print("\n💰 Test 8: Balance final...")
        balance_after = self.get_balance()
        pnl = balance_after - balance_before
        results['tests']['balance_final'] = f'✅ ${balance_after:.2f} (PnL: ${pnl:.4f})'
        
        # Resultado final
        all_passed = all('✅' in v or 'PASS' in v for v in results['tests'].values())
        results['status'] = '🎉 ALL TESTS PASSED' if all_passed else '⚠️ SOME TESTS FAILED'
        
        return results


def run_demo_test():
    """Ejecutar prueba de demo."""
    print("\n" + "=" * 60)
    print("ANTIGRAVITY HIGH - DEMO ORDER TEST")
    print("Motor: B1_SPRINT | Symbol: BTCUSDT")
    print("=" * 60)
    
    try:
        tester = DemoOrderTester(motor='B1')
        results = tester.run_full_test()
        
        print("\n" + "=" * 60)
        print("RESULTADOS DE LA PRUEBA")
        print("=" * 60)
        
        for test, result in results['tests'].items():
            print(f"  {test}: {result}")
        
        print("\n" + "=" * 60)
        print(f"ESTADO FINAL: {results['status']}")
        print("=" * 60)
        
        return results
        
    except Exception as e:
        print(f"\n❌ Error crítico: {str(e)}")
        return {'status': f'❌ CRITICAL ERROR: {str(e)}'}


if __name__ == '__main__':
    run_demo_test()
