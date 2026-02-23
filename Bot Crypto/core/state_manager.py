import os
import logging
import json
from datetime import datetime
from supabase import create_client, Client

logger = logging.getLogger('Core.StateManager')

class StateManager:
    """
    Gestor de Estado Persistente (Supabase).
    Permite sobrevivir a reinicios de Railway sin perder contexto.
    """
    def __init__(self):
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_ANON_KEY")
        
        if not url or not key:
            logger.warning("⚠️ Supabase creds no encontradas. Persistencia DESACTIVADA.")
            self.supabase = None
        else:
            try:
                self.supabase: Client = create_client(url, key)
                logger.info("✅ Conectado a Supabase.")
            except Exception as e:
                logger.error(f"❌ Error conectando a Supabase: {e}")
                self.supabase = None

    async def save_position(self, motor_id: str, symbol: str, data: dict):
        """Guarda o actualiza una posición abierta."""
        if not self.supabase: return
        
        try:
            # Upsert logic
            period_data = {
                "motor_id": motor_id,
                "symbol": symbol,
                "data": json.dumps(data),
                "updated_at": datetime.now().isoformat()
            }
            
            # Asumimos una tabla 'bot_positions' con unique key (motor_id, symbol)
            # O simplemente insertamos logs.
            # Para estado activo, mejor usar una tabla de 'active_positions'.
            
            self.supabase.table("bot_active_positions").upsert(
                period_data, on_conflict="motor_id, symbol"
            ).execute()
            
        except Exception as e:
            logger.error(f"❌ Error guardando estado en DB: {e}")

    async def load_active_positions(self) -> dict:
        """Recupera todas las posiciones activas al inicio."""
        if not self.supabase: return {}
        
        try:
            response = self.supabase.table("bot_active_positions").select("*").execute()
            positions = {}
            for row in response.data:
                motor = row['motor_id']
                if motor not in positions:
                    positions[motor] = {}
                positions[motor][row['symbol']] = json.loads(row['data'])
            return positions
        except Exception as e:
            logger.error(f"❌ Error cargando estado de DB: {e}")
            return {}

    async def log_trade(self, trade_data: dict):
        """Registra un trade histórico."""
        if not self.supabase: return
        try:
            self.supabase.table("bot_trade_history").insert(trade_data).execute()
        except Exception as e:
            logger.error(f"❌ Error logueando trade: {e}")
