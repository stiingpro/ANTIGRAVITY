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
        },
        'TRIFECTA': {
            'name': 'TRIFECTA_GLOBAL',
            'profile': 'Orchestrator',
            'max_leverage': 10,
            'margin_type': 'ISOLATED',
            'position_mode': 'Hedge'
        }
    }


class ExchangeConnector:
    """
    Conector seguro para Binance Futures.
    Maneja autenticación, conexión y configuración de margen.
    """
    
    def __init__(
        self,
        motor: Literal['B1', 'B2', 'B3', 'TRIFECTA'],
        environment: Literal['testnet', 'production'] = 'testnet',
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        testnet: bool = False # Compatibilidad con main.py anterior
    ):
        """
        Inicializa el conector.
        
        Args:
            motor: Identificador del motor (B1, B2, B3, TRIFECTA)
            environment: Entorno a usar (testnet o production)
            api_key: (Opcional) Inyección manual de key
            api_secret: (Opcional) Inyección manual de secret
        """
        self.motor = motor
        
        # Compatibilidad: si pasan testnet=True, forzar environment='testnet'
        if testnet and environment == 'production': 
             environment = 'testnet'
             
        self.environment = environment
        self.config = ExchangeConfig.ENVIRONMENTS[environment]
        self.motor_config = ExchangeConfig.MOTORS[motor]
        
        # Credenciales manuales o cargar de env
        self.api_key = api_key
        self.api_secret = api_secret
        
        if not self.api_key or not self.api_secret:
            self._load_credentials()
        
        # Estado de conexión
        self.connected = False
        self.client = None
        
        logger.info(f"🚀 Inicializando {motor} en {environment.upper()}")
        logger.info(f"   API URL: {self.config['api_url']}")
    
    def _load_credentials(self) -> None:
        """Carga las credenciales desde el archivo .env correspondiente o intenta fallbacks."""
        
        # Determinar qué archivo .env cargar
        if self.environment == 'testnet':
            env_file = '.env.testnet'
            key_prefix = f'{self.motor}_TESTNET'
        else:
            env_file = '.env.production'
            key_prefix = self.motor
        
        # Cargar archivo .env local si existe
        env_path = os.path.join(os.path.dirname(__file__), env_file)
        if os.path.exists(env_path):
            load_dotenv(env_path)
            logger.info(f"✅ Cargado: {env_file}")
        
        # Estrategia de búsqueda de credenciales (Cascada)
        # 1. Prefijo específico (ej. TRIFECTA_TESTNET)
        # 2. Fallback a B1 (ej. B1_TESTNET)
        # 3. Fallback a Genericos (BINANCE)
        # 4. Fallback Cruzado (ej. probar Production keys si estamos en Testnet y viceversa, como último recurso desesperado)
        
        candidates = [
            key_prefix,                          # TRIFECTA_TESTNET
            f'B1_{"TESTNET" if "TESTNET" in key_prefix else ""}'.rstrip("_"), # B1_TESTNET
            'BINANCE',                           # BINANCE
            'B1',                                # B1 (Prod key usada en testnet?)
            'B2_TESTNET',
            'B3_TESTNET'
        ]
        
        for candidate in candidates:
            k = os.getenv(f'{candidate}_API_KEY')
            s = os.getenv(f'{candidate}_API_SECRET')
            if k and s:
                self.api_key = k
                self.api_secret = s
                logger.info(f"🔑 Credenciales encontradas usando: {candidate}")
                return

        # Si llegamos aquí, falló todo
        logger.error(f"❌ Credenciales NO encontradas. Se probaron: {candidates}")
        raise ValueError(f"Missing credentials for {key_prefix} and all fallbacks")
    
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

    async def execute_with_retry(
        self,
        fn,
        *args,
        max_retries: int = 3,
        base_delay: float = 0.5,
        **kwargs
    ):
        """
        Execute a Binance API call with exponential backoff retry.
        
        Catches rate-limit errors (HTTP 429, -1015) and retries.
        Delays: 0.5s → 1.0s → 2.0s (exponential).
        
        Args:
            fn: The function to call (sync or async)
            max_retries: Maximum retry attempts
            base_delay: Initial delay in seconds (doubles each retry)
        
        Returns:
            Result of fn(*args, **kwargs)
            
        Raises:
            Last exception if all retries exhausted
        """
        import asyncio
        
        last_error = None
        
        for attempt in range(1, max_retries + 1):
            try:
                # Support both sync and async callables
                if asyncio.iscoroutinefunction(fn):
                    result = await fn(*args, **kwargs)
                else:
                    result = fn(*args, **kwargs)
                return result
                
            except Exception as e:
                last_error = e
                error_str = str(e)
                
                # Identify rate-limit errors
                is_rate_limit = (
                    '429' in error_str or
                    '-1015' in error_str or
                    'Too many' in error_str.lower() or
                    'rate limit' in error_str.lower()
                )
                
                if attempt < max_retries:
                    delay = base_delay * (2 ** (attempt - 1))
                    
                    if is_rate_limit:
                        logger.warning(
                            f"⏳ Rate limit hit (attempt {attempt}/{max_retries}), "
                            f"retrying in {delay:.1f}s: {error_str[:100]}"
                        )
                    else:
                        logger.warning(
                            f"⚠️ API error (attempt {attempt}/{max_retries}), "
                            f"retrying in {delay:.1f}s: {error_str[:100]}"
                        )
                    
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"❌ All {max_retries} retries exhausted: {error_str[:200]}"
                    )
        
        raise last_error

    def change_leverage(self, symbol: str, leverage: int):
        """Wrapper para cambiar apalancamiento."""
        if not self.connected:
            raise RuntimeError("No conectado.")
        try:
            return self.client.futures_change_leverage(symbol=symbol, leverage=leverage)
        except Exception as e:
            logger.error(f"❌ Error change_leverage {symbol}: {e}")
            raise
    
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
                        'total': float(asset.get('walletBalance', 0)),
                        'available': float(asset.get('availableBalance', 0)),
                        'unrealized_pnl': float(asset.get('unrealizedProfit', 0))
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
                            'leverage': int(p.get('leverage', 1)),
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
