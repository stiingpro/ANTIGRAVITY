"""
ANTIGRAVITY HIGH - TRIFECTA PERFECTA
Módulo de Conexión a Exchange (Testnet + Production)
=====================================================
Este módulo maneja la conexión segura a Binance Futures,
soportando tanto Testnet (pruebas) como Production (real).

Uso:
    from exchange_connector import ExchangeConnector
    
    # Para Testnet (pruebas)
    connector = ExchangeConnector(motor='B1', environment='testnet')
    
    # Para Production (dinero real)
    connector = ExchangeConnector(motor='B1', environment='production')
"""

import os
import logging
from typing import Dict, Optional, Literal
from datetime import datetime
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ExchangeConnector')


class ExchangeConfig:
    """Configuración de URLs y endpoints para cada entorno."""
    
    ENVIRONMENTS = {
        'testnet': {
            'name': 'Binance Futures Testnet',
            'api_url': 'https://testnet.binancefuture.com',
            'ws_url': 'wss://stream.binancefuture.com',
            'web_url': 'https://testnet.binancefuture.com',
            'is_testnet': True
        },
        'production': {
            'name': 'Binance Futures Production',
            'api_url': 'https://fapi.binance.com',
            'ws_url': 'wss://fstream.binance.com',
            'web_url': 'https://www.binance.com/futures',
            'is_testnet': False
        }
    }
    
    MOTORS = {
        'B1': {
            'name': 'B1_SPRINT',
            'profile': 'Aggressive',
            'max_leverage': 20,
            'margin_type': 'ISOLATED',
            'position_mode': 'Hedge'  # Permite Long y Short simultáneo
        },
        'B2': {
            'name': 'B2_RESILIENCE', 
            'profile': 'Moderate',
            'max_leverage': 5,
            'margin_type': 'ISOLATED',
            'position_mode': 'Hedge'
        },
        'B3': {
            'name': 'B3_ANCHOR',
            'profile': 'Conservative',
            'max_leverage': 3,
            'margin_type': 'ISOLATED',
            'position_mode': 'Hedge'  # Permite Long y Short simultáneo
        }
    }


class ExchangeConnector:
    """
    Conector seguro para Binance Futures.
    Maneja autenticación, conexión y configuración de margen.
    """
    
    def __init__(
        self,
        motor: Literal['B1', 'B2', 'B3'],
        environment: Literal['testnet', 'production'] = 'testnet'
    ):
        """
        Inicializa el conector.
        
        Args:
            motor: Identificador del motor (B1, B2, B3)
            environment: Entorno a usar (testnet o production)
        """
        self.motor = motor
        self.environment = environment
        self.config = ExchangeConfig.ENVIRONMENTS[environment]
        self.motor_config = ExchangeConfig.MOTORS[motor]
        
        # Cargar credenciales
        self._load_credentials()
        
        # Estado de conexión
        self.connected = False
        self.client = None
        
        logger.info(f"🚀 Inicializando {motor} en {environment.upper()}")
        logger.info(f"   API URL: {self.config['api_url']}")
    
    def _load_credentials(self) -> None:
        """Carga las credenciales desde el archivo .env correspondiente."""
        
        # Determinar qué archivo .env cargar
        if self.environment == 'testnet':
            env_file = '.env.testnet'
            key_prefix = f'{self.motor}_TESTNET'
        else:
            env_file = '.env.production'
            key_prefix = self.motor
        
        # Cargar archivo .env
        env_path = os.path.join(os.path.dirname(__file__), env_file)
        
        if os.path.exists(env_path):
            load_dotenv(env_path)
            logger.info(f"✅ Cargado: {env_file}")
        else:
            logger.warning(f"⚠️ Archivo no encontrado: {env_file}")
            logger.warning(f"   Buscando en variables de entorno...")
        
        # Obtener credenciales
        self.api_key = os.getenv(f'{key_prefix}_API_KEY')
        self.api_secret = os.getenv(f'{key_prefix}_API_SECRET')
        
        if not self.api_key or not self.api_secret:
            logger.error(f"❌ Credenciales no encontradas para {key_prefix}")
            raise ValueError(f"Missing credentials for {key_prefix}")
    
    def connect(self) -> bool:
        """
        Establece conexión con el exchange.
        
        Returns:
            True si la conexión fue exitosa
        """
        try:
            # Importar binance solo si está disponible
            try:
                from binance.client import Client
                from binance.exceptions import BinanceAPIException
            except ImportError:
                logger.error("❌ Librería 'python-binance' no instalada")
                logger.error("   Ejecutar: pip install python-binance")
                return False
            
            # Crear cliente con las URLs correctas
            self.client = Client(
                api_key=self.api_key,
                api_secret=self.api_secret,
                testnet=self.config['is_testnet']
            )
            
            # Si es testnet, configurar URLs manualmente
            if self.config['is_testnet']:
                self.client.FUTURES_URL = self.config['api_url']
            
            # Verificar conexión
            server_time = self.client.futures_time()
            self.connected = True
            
            logger.info(f"✅ Conectado a {self.config['name']}")
            logger.info(f"   Server time: {datetime.fromtimestamp(server_time['serverTime']/1000)}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error de conexión: {str(e)}")
            self.connected = False
            return False
    
    def configure_margin(self, symbol: str = 'BTCUSDT') -> Dict:
        """
        Configura el tipo de margen y apalancamiento según el motor.
        
        Args:
            symbol: Par de trading (default: BTCUSDT)
            
        Returns:
            Dict con el resultado de la configuración
        """
        if not self.connected:
            raise RuntimeError("No conectado. Llamar connect() primero.")
        
        results = {}
        
        try:
            # 1. Configurar tipo de margen (ISOLATED)
            try:
                self.client.futures_change_margin_type(
                    symbol=symbol,
                    marginType=self.motor_config['margin_type']
                )
                results['margin_type'] = f"✅ {self.motor_config['margin_type']}"
            except Exception as e:
                if 'No need to change margin type' in str(e):
                    results['margin_type'] = f"✅ Ya en {self.motor_config['margin_type']}"
                else:
                    results['margin_type'] = f"❌ Error: {str(e)}"
            
            # 2. Configurar apalancamiento
            try:
                leverage_response = self.client.futures_change_leverage(
                    symbol=symbol,
                    leverage=self.motor_config['max_leverage']
                )
                results['leverage'] = f"✅ {leverage_response['leverage']}x"
            except Exception as e:
                results['leverage'] = f"❌ Error: {str(e)}"
            
            # 3. Configurar modo de posición (Hedge o One-Way)
            try:
                position_mode = self.motor_config['position_mode'] == 'Hedge'
                self.client.futures_change_position_mode(dualSidePosition=position_mode)
                results['position_mode'] = f"✅ {self.motor_config['position_mode']}"
            except Exception as e:
                if 'No need to change position side' in str(e):
                    results['position_mode'] = f"✅ Ya en {self.motor_config['position_mode']}"
                else:
                    results['position_mode'] = f"❌ Error: {str(e)}"
            
            logger.info(f"⚙️ Configuración para {symbol}:")
            for key, value in results.items():
                logger.info(f"   {key}: {value}")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Error configurando margen: {str(e)}")
            raise
    
    def get_balance(self) -> Dict:
        """
        Obtiene el balance de la cuenta.
        
        Returns:
            Dict con el balance USDT
        """
        if not self.connected:
            raise RuntimeError("No conectado. Llamar connect() primero.")
        
        try:
            account = self.client.futures_account()
            
            # Buscar balance de USDT
            usdt_balance = None
            for asset in account['assets']:
                if asset['asset'] == 'USDT':
                    usdt_balance = {
                        'total': float(asset['walletBalance']),
                        'available': float(asset['availableBalance']),
                        'unrealized_pnl': float(asset['unrealizedProfit'])
                    }
                    break
            
            if usdt_balance:
                logger.info(f"💰 Balance {self.motor}:")
                logger.info(f"   Total: ${usdt_balance['total']:.2f} USDT")
                logger.info(f"   Disponible: ${usdt_balance['available']:.2f} USDT")
                logger.info(f"   PnL No Realizado: ${usdt_balance['unrealized_pnl']:.2f} USDT")
            
            return usdt_balance or {}
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo balance: {str(e)}")
            raise
    
    def get_open_positions(self) -> list:
        """
        Obtiene las posiciones abiertas.
        
        Returns:
            Lista de posiciones con cantidad != 0
        """
        if not self.connected:
            raise RuntimeError("No conectado. Llamar connect() primero.")
        
        try:
            positions = self.client.futures_position_information()
            
            # Filtrar solo posiciones abiertas
            # Filtrar solo posiciones abiertas
            open_positions = []
            for p in positions:
                try:
                    if float(p.get('positionAmt', 0)) != 0:
                        open_positions.append({
                            'symbol': p.get('symbol'),
                            'side': 'LONG' if float(p.get('positionAmt', 0)) > 0 else 'SHORT',
                            'quantity': abs(float(p.get('positionAmt', 0))),
                            'entry_price': float(p.get('entryPrice', 0)),
                            'pnl': float(p.get('unRealizedProfit', 0)),
                            'leverage': int(p.get('leverage', 1)),  # Default to 1 if missing
                            'margin_type': p.get('marginType', 'ISOLATED')
                        })
                except Exception as e:
                    logger.error(f"⚠️ Error procesando posición: {str(e)} | Keys: {list(p.keys())}")
                    continue
            
            if open_positions:
                logger.info(f"📊 Posiciones abiertas ({len(open_positions)}):")
                for pos in open_positions:
                    emoji = '🟢' if pos['pnl'] >= 0 else '🔴'
                    logger.info(f"   {emoji} {pos['symbol']} {pos['side']} "
                              f"x{pos['leverage']} | PnL: ${pos['pnl']:.2f}")
            else:
                logger.info("📊 No hay posiciones abiertas")
            
            return open_positions
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo posiciones: {str(e)}")
            raise
    
    def test_connection(self) -> Dict:
        """
        Prueba completa de conexión.
        
        Returns:
            Dict con resultados de todas las pruebas
        """
        results = {
            'motor': self.motor,
            'environment': self.environment,
            'timestamp': datetime.now().isoformat(),
            'tests': {}
        }
        
        # Test 1: Conexión
        try:
            self.connect()
            results['tests']['connection'] = '✅ PASS'
        except Exception as e:
            results['tests']['connection'] = f'❌ FAIL: {str(e)}'
            return results
        
        # Test 2: Balance
        try:
            balance = self.get_balance()
            results['tests']['balance'] = f"✅ PASS (${balance.get('total', 0):.2f} USDT)"
        except Exception as e:
            results['tests']['balance'] = f'❌ FAIL: {str(e)}'
        
        # Test 3: Configuración de margen
        try:
            margin_config = self.configure_margin('BTCUSDT')
            results['tests']['margin_config'] = '✅ PASS'
            results['margin_details'] = margin_config
        except Exception as e:
            results['tests']['margin_config'] = f'❌ FAIL: {str(e)}'
        
        # Test 4: Posiciones
        try:
            positions = self.get_open_positions()
            results['tests']['positions'] = f'✅ PASS ({len(positions)} abiertas)'
        except Exception as e:
            results['tests']['positions'] = f'❌ FAIL: {str(e)}'
        
        # Resumen
        all_passed = all('✅' in v for v in results['tests'].values())
        results['status'] = '🎉 ALL TESTS PASSED' if all_passed else '⚠️ SOME TESTS FAILED'
        
        return results


def run_testnet_validation():
    """
    Script de validación del Testnet.
    Ejecutar antes de pasar a producción.
    """
    print("=" * 60)
    print("ANTIGRAVITY HIGH - VALIDACIÓN TESTNET")
    print("=" * 60)
    
    motors_to_test = ['B1', 'B2', 'B3']
    all_results = []
    
    for motor in motors_to_test:
        print(f"\n{'='*20} {motor} {'='*20}")
        try:
            connector = ExchangeConnector(motor=motor, environment='testnet')
            results = connector.test_connection()
            all_results.append(results)
            
            print(f"\nResultados para {motor}:")
            for test, result in results['tests'].items():
                print(f"  {test}: {result}")
            print(f"\nEstado: {results['status']}")
            
        except Exception as e:
            print(f"❌ Error crítico para {motor}: {str(e)}")
            all_results.append({'motor': motor, 'status': f'❌ CRITICAL ERROR: {str(e)}'})
    
    print("\n" + "=" * 60)
    print("RESUMEN FINAL")
    print("=" * 60)
    
    for r in all_results:
        print(f"  {r.get('motor', 'Unknown')}: {r.get('status', 'Unknown')}")
    
    return all_results


if __name__ == '__main__':
    # Ejecutar validación cuando se corre directamente
    run_testnet_validation()
