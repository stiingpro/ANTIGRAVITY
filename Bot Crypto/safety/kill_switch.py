"""
Kill Switch Module
==================
Corte de emergencia automático.
Activa cuando drawdown > 15%
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict

logger = logging.getLogger('KillSwitch')


class KillSwitch:
    """
    Kill Switch de emergencia.
    
    Funciones:
    - Monitorear drawdown
    - Cerrar todas las posiciones
    - Activar hibernación
    - Notificar vía Telegram
    """
    
    def __init__(
        self,
        max_drawdown_pct: float = 15.0,
        hibernation_hours: int = 24,
        connector = None
    ):
        self.max_drawdown_pct = max_drawdown_pct
        self.hibernation_hours = hibernation_hours
        self.connector = connector
        
        self.is_active = False
        self.activation_time: Optional[datetime] = None
        self.hibernation_until: Optional[datetime] = None
        
        logger.info(f"🛑 Kill Switch configurado: {max_drawdown_pct}% drawdown")
    
    def check_trigger(
        self,
        initial_balance: float,
        current_balance: float
    ) -> bool:
        """
        Verificar si debe activarse el kill switch.
        
        Returns:
            True si el kill switch debe activarse
        """
        if self.is_active:
            return True
        
        if initial_balance <= 0:
            return False
        
        drawdown_pct = ((initial_balance - current_balance) / initial_balance) * 100
        
        if drawdown_pct >= self.max_drawdown_pct:
            logger.critical(
                f"🚨 TRIGGER KILL SWITCH - Drawdown: {drawdown_pct:.2f}% "
                f"(límite: {self.max_drawdown_pct}%)"
            )
            return True
        
        return False
    
    async def activate(self) -> bool:
        """
        Activar kill switch:
        1. Cerrar todas las posiciones
        2. Cancelar órdenes pendientes
        3. Iniciar hibernación
        """
        if self.is_active:
            logger.warning("Kill switch ya está activo")
            return True
        
        logger.critical("=" * 60)
        logger.critical("🚨🚨🚨 KILL SWITCH ACTIVADO 🚨🚨🚨")
        logger.critical("=" * 60)
        
        self.is_active = True
        self.activation_time = datetime.now()
        self.hibernation_until = datetime.now() + timedelta(hours=self.hibernation_hours)
        
        try:
            # Cerrar todas las posiciones
            if self.connector and self.connector.connected:
                await self._emergency_close_all()
            
            # Notificar
            await self._send_alert()
            
            logger.critical(
                f"⏸️ Hibernación hasta: {self.hibernation_until.isoformat()}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error durante activación: {e}")
            return False
    
    async def _emergency_close_all(self):
        """Cierre de emergencia de todas las posiciones."""
        try:
            # Obtener todas las posiciones
            positions = self.connector.client.futures_position_information()
            
            for pos in positions:
                amount = float(pos['positionAmt'])
                symbol = pos['symbol']
                
                if amount != 0:
                    # Determinar lado de cierre
                    close_side = 'SELL' if amount > 0 else 'BUY'
                    
                    # Cerrar con orden de mercado
                    self.connector.client.futures_create_order(
                        symbol=symbol,
                        side=close_side,
                        type='MARKET',
                        quantity=abs(amount)
                    )
                    logger.info(f"✅ Cerrada posición {symbol}: {amount}")
            
            # Cancelar todas las órdenes pendientes
            for pos in positions:
                if float(pos['positionAmt']) != 0:
                    try:
                        self.connector.client.futures_cancel_all_open_orders(
                            symbol=pos['symbol']
                        )
                    except:
                        pass
            
            logger.info("✅ Todas las posiciones cerradas")
            
        except Exception as e:
            logger.error(f"Error en cierre de emergencia: {e}")
    
    async def _send_alert(self):
        """Enviar alerta de kill switch."""
        import os
        
        try:
            telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
            telegram_chat = os.getenv('TELEGRAM_CHAT_ID')
            
            if telegram_token and telegram_chat:
                import aiohttp
                
                message = (
                    "🚨 *KILL SWITCH ACTIVADO*\n\n"
                    f"⏰ Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"⏸️ Hibernación: {self.hibernation_hours}h\n"
                    f"📊 Reactivación: {self.hibernation_until.strftime('%Y-%m-%d %H:%M')}\n\n"
                    "Todas las posiciones han sido cerradas.\n"
                    "Revisar manualmente antes de reactivar."
                )
                
                url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
                
                async with aiohttp.ClientSession() as session:
                    await session.post(url, json={
                        'chat_id': telegram_chat,
                        'text': message,
                        'parse_mode': 'Markdown'
                    })
                
                logger.info("📱 Alerta Telegram enviada")
            else:
                logger.warning("⚠️ Telegram no configurado")
                
        except Exception as e:
            logger.error(f"Error enviando alerta: {e}")
    
    def can_resume(self) -> bool:
        """Verificar si la hibernación ha terminado."""
        if not self.is_active:
            return True
        
        if self.hibernation_until is None:
            return False
        
        return datetime.now() >= self.hibernation_until
    
    def deactivate(self) -> bool:
        """Desactivar kill switch (después de hibernación)."""
        if not self.can_resume():
            remaining = self.hibernation_until - datetime.now()
            logger.warning(
                f"⏸️ Hibernación activa. Tiempo restante: {remaining}"
            )
            return False
        
        self.is_active = False
        self.activation_time = None
        self.hibernation_until = None
        
        logger.info("✅ Kill switch desactivado - Sistema puede reanudar")
        
        return True
    
    def get_status(self) -> Dict:
        """Obtener estado del kill switch."""
        return {
            'is_active': self.is_active,
            'max_drawdown_pct': self.max_drawdown_pct,
            'hibernation_hours': self.hibernation_hours,
            'activation_time': self.activation_time.isoformat() if self.activation_time else None,
            'hibernation_until': self.hibernation_until.isoformat() if self.hibernation_until else None,
            'can_resume': self.can_resume()
        }
