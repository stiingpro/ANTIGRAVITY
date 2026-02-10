"""
ANTIGRAVITY HIGH - TRIFECTA PERFECTA
Módulo de Bóveda de Credenciales API
=====================================
Este módulo proporciona cifrado AES-256 para proteger las credenciales API
en reposo. Las claves se descifran solo en memoria durante la ejecución.

⚠️ NUNCA imprimir ni loguear credenciales descifradas.
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict
from cryptography.fernet import Fernet


class APIVault:
    """
    Bóveda segura para credenciales API con cifrado AES-256.
    
    Las claves se cifran en reposo y solo se descifran en memoria.
    Compatible con el sistema de motores B1, B2, B3.
    """
    
    VALID_MOTORS = ['MASTER', 'B1', 'B2', 'B3', 'MONITOR']
    
    def __init__(self, vault_key_path: Optional[str] = None):
        """
        Inicializa la bóveda.
        
        Args:
            vault_key_path: Ruta al archivo de clave maestra.
                           Por defecto: /etc/antigravity/vault.key (Linux)
                           o %APPDATA%/antigravity/vault.key (Windows)
        """
        if vault_key_path is None:
            if os.name == 'nt':  # Windows
                vault_key_path = os.path.join(
                    os.environ.get('APPDATA', '.'), 
                    'antigravity', 
                    'vault.key'
                )
            else:  # Linux/Mac
                vault_key_path = '/etc/antigravity/vault.key'
        
        self.vault_key_path = vault_key_path
        self.vault_key = self._load_or_create_key()
        self.cipher = Fernet(self.vault_key)
    
    def _load_or_create_key(self) -> bytes:
        """Carga o genera la clave maestra de la bóveda."""
        path = Path(self.vault_key_path)
        
        if path.exists():
            with open(path, 'rb') as f:
                return f.read()
        else:
            # Generar nueva clave
            key = Fernet.generate_key()
            
            # Crear directorio si no existe
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Guardar clave con permisos restrictivos
            with open(path, 'wb') as f:
                f.write(key)
            
            # Establecer permisos (solo owner puede leer)
            if os.name != 'nt':  # Linux/Mac
                os.chmod(path, 0o600)
            
            print(f"⚠️ Nueva clave de bóveda generada en: {path}")
            print("⚠️ RESPALDAR ESTA CLAVE DE FORMA SEGURA")
            
            return key
    
    def encrypt_secret(self, secret: str) -> str:
        """
        Cifra un secreto para almacenamiento seguro.
        
        Args:
            secret: El secreto en texto plano a cifrar.
            
        Returns:
            El secreto cifrado como string base64.
        """
        return self.cipher.encrypt(secret.encode()).decode()
    
    def decrypt_secret(self, encrypted: str) -> str:
        """
        Descifra un secreto en memoria.
        
        Args:
            encrypted: El secreto cifrado.
            
        Returns:
            El secreto descifrado.
            
        ⚠️ NUNCA loguear ni imprimir el resultado.
        """
        return self.cipher.decrypt(encrypted.encode()).decode()
    
    def get_api_credentials(self, motor: str) -> Dict[str, str]:
        """
        Obtiene las credenciales API para un motor específico.
        
        Args:
            motor: Nombre del motor ('B1', 'B2', 'B3', 'MASTER', 'MONITOR')
            
        Returns:
            Diccionario con 'api_key' y 'api_secret' descifrados.
            
        Raises:
            ValueError: Si el motor no es válido.
            EnvironmentError: Si las variables de entorno no existen.
        """
        motor = motor.upper()
        
        if motor not in self.VALID_MOTORS:
            raise ValueError(
                f"Motor '{motor}' no válido. "
                f"Opciones: {self.VALID_MOTORS}"
            )
        
        # Intentar cargar versión cifrada primero
        encrypted_key = os.environ.get(f"{motor}_API_KEY_ENC")
        encrypted_secret = os.environ.get(f"{motor}_API_SECRET_ENC")
        
        if encrypted_key and encrypted_secret:
            return {
                "api_key": self.decrypt_secret(encrypted_key),
                "api_secret": self.decrypt_secret(encrypted_secret)
            }
        
        # Fallback a versión no cifrada (desarrollo)
        plain_key = os.environ.get(f"{motor}_API_KEY")
        plain_secret = os.environ.get(f"{motor}_API_SECRET")
        
        if plain_key and plain_secret:
            return {
                "api_key": plain_key,
                "api_secret": plain_secret
            }
        
        raise EnvironmentError(
            f"Credenciales para motor '{motor}' no encontradas. "
            f"Verificar variables: {motor}_API_KEY, {motor}_API_SECRET"
        )
    
    def get_motor_config(self, motor: str) -> Dict[str, any]:
        """
        Obtiene la configuración completa de un motor.
        
        Args:
            motor: Nombre del motor ('B1', 'B2', 'B3')
            
        Returns:
            Diccionario con todas las configuraciones del motor.
        """
        motor = motor.upper()
        credentials = self.get_api_credentials(motor)
        
        return {
            **credentials,
            "exchange": os.environ.get(f"{motor}_EXCHANGE", "binance"),
            "subaccount_id": os.environ.get(f"{motor}_SUBACCOUNT_ID", f"{motor}_DEFAULT"),
            "max_leverage": int(os.environ.get(f"{motor}_MAX_LEVERAGE", "1")),
            "capital_limit": float(os.environ.get(f"{motor}_CAPITAL_LIMIT", "1000"))
        }
    
    def validate_environment(self) -> Dict[str, bool]:
        """
        Valida que todas las variables de entorno requeridas existan.
        
        Returns:
            Diccionario con el estado de validación por motor.
        """
        results = {}
        
        for motor in self.VALID_MOTORS:
            has_encrypted = (
                os.environ.get(f"{motor}_API_KEY_ENC") and 
                os.environ.get(f"{motor}_API_SECRET_ENC")
            )
            has_plain = (
                os.environ.get(f"{motor}_API_KEY") and 
                os.environ.get(f"{motor}_API_SECRET")
            )
            results[motor] = has_encrypted or has_plain
        
        return results


def encrypt_env_file(input_path: str, output_path: str, vault: APIVault) -> None:
    """
    Cifra un archivo .env y genera versión segura.
    
    Args:
        input_path: Ruta al .env original con claves en texto plano.
        output_path: Ruta donde guardar el .env cifrado.
        vault: Instancia de APIVault para cifrado.
    """
    with open(input_path, 'r') as f:
        lines = f.readlines()
    
    encrypted_lines = []
    
    for line in lines:
        line = line.strip()
        
        # Mantener comentarios y líneas vacías
        if not line or line.startswith('#'):
            encrypted_lines.append(line)
            continue
        
        # Procesar variables
        if '=' in line:
            key, value = line.split('=', 1)
            
            # Cifrar solo las claves API sensibles
            if 'API_KEY' in key or 'API_SECRET' in key or 'TOKEN' in key:
                if not value.startswith('your_'):  # No cifrar placeholders
                    encrypted_value = vault.encrypt_secret(value)
                    key = key.replace('API_KEY', 'API_KEY_ENC')
                    key = key.replace('API_SECRET', 'API_SECRET_ENC')
                    key = key.replace('TOKEN', 'TOKEN_ENC')
                    encrypted_lines.append(f"{key}={encrypted_value}")
                    continue
            
            encrypted_lines.append(line)
    
    with open(output_path, 'w') as f:
        f.write('\n'.join(encrypted_lines))
    
    print(f"✅ Archivo cifrado generado: {output_path}")
    print("⚠️ ELIMINAR el archivo original con credenciales en texto plano")


if __name__ == "__main__":
    # Test de la bóveda
    print("=" * 50)
    print("ANTIGRAVITY - API Vault Test")
    print("=" * 50)
    
    vault = APIVault()
    
    # Validar entorno
    status = vault.validate_environment()
    print("\nEstado de credenciales:")
    for motor, ok in status.items():
        icon = "✅" if ok else "❌"
        print(f"  {icon} {motor}: {'Configurado' if ok else 'FALTANTE'}")
    
    print("\n" + "=" * 50)
