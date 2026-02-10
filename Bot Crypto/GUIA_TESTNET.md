# 🧪 Guía de Configuración - Binance Testnet

## ¿Qué es el Testnet?

El **Testnet** es una réplica de Binance que usa **dinero ficticio** (gratis). Permite:
- Probar el bot sin riesgo
- Verificar que las APIs funcionan
- Practicar antes de usar dinero real

---

## Paso 1: Crear cuenta en Testnet

1. Ve a: **https://testnet.binancefuture.com/**
2. Click en **"Log In"** (arriba derecha)
3. Usa tu cuenta de **GitHub** para autenticarte (requerido)
4. Una vez dentro, automáticamente tienes **USDT ficticio** para probar

---

## Paso 2: Crear API Keys del Testnet

1. En el Testnet, ve al ícono de usuario → **"API Management"**
2. Click en **"Create API"**
3. Nombra la API: `TESTNET_B1_SPRINT`
4. Copia:
   - **API Key** 
   - **Secret Key**
5. Repite para otros 2 motores (opcional para pruebas iniciales)

---

## Paso 3: Configurar el archivo .env.testnet

Abre el archivo `.env.testnet` y reemplaza los valores:

```env
# MOTOR B1: SPRINT (Testnet)
B1_TESTNET_API_KEY=tu_api_key_del_testnet_aqui
B1_TESTNET_API_SECRET=tu_secret_key_del_testnet_aqui
```

---

## Paso 4: Instalar dependencias

```powershell
cd "d:\ANTIGRAVITY\Bot Crypto"
pip install python-binance python-dotenv
```

---

## Paso 5: Ejecutar prueba de conexión

```powershell
cd "d:\ANTIGRAVITY\Bot Crypto"
python exchange_connector.py
```

### Resultado esperado:

```
ANTIGRAVITY HIGH - VALIDACIÓN TESTNET
============================================================

==================== B1 ====================
🚀 Inicializando B1 en TESTNET
   API URL: https://testnet.binancefuture.com
✅ Conectado a Binance Futures Testnet
💰 Balance B1:
   Total: $10000.00 USDT
   Disponible: $10000.00 USDT
⚙️ Configuración para BTCUSDT:
   margin_type: ✅ ISOLATED
   leverage: ✅ 20x
   position_mode: ✅ Hedge

Estado: 🎉 ALL TESTS PASSED
```

---

## Checklist de Validación

| Test | Esperado |
|------|----------|
| Conexión al servidor | ✅ PASS |
| Lectura de balance | ✅ PASS (USDT ficticio) |
| Configuración ISOLATED | ✅ PASS |
| Configuración leverage | ✅ PASS |

---

## ⚠️ Diferencias Testnet vs Production

| Aspecto | Testnet | Production |
|---------|---------|------------|
| Dinero | Ficticio (gratis) | Real (tu capital) |
| URLs | testnet.binancefuture.com | fapi.binance.com |
| API Keys | Diferentes | Las que creaste hoy |
| Riesgo | Ninguno | Total |

---

## Próximo paso

Una vez que el Testnet funcione correctamente:
1. ✅ Validar los 3 motores en Testnet
2. ✅ Probar operaciones básicas (abrir/cerrar posición)
3. 🔄 Migrar a Production con las APIs reales
