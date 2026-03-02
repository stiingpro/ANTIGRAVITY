# 📋 Bot Crypto — Registro Completo de Actualizaciones

> **Última actualización:** 2 de marzo de 2026  
> **Repositorio:** `Bot Crypto` (deploy automático en Railway)  
> **Entorno:** Binance Futures Testnet (hedge mode)

---

## 🏗️ Arquitectura General

El proyecto es un **sistema de trading automatizado** ("Trifecta Perfecta") con 3 motores que operan en paralelo, cada uno con su propia estrategia:

| Motor | Estilo | Timeframe | Pares Principales |
|-------|--------|-----------|-------------------|
| **B1 Sprint** | Scalping agresivo | 5m / 15m | SOLUSDT |
| **B2 Resilience** | Swing trading | 1H / 4H | DOTUSDT, AVAXUSDT |
| **B3 Anchor** | Posiciones de largo plazo | 4H / 1D | LINKUSDT, DOTUSDT |

### Componentes Core
- `main.py` — Orquestador `TrifectaOrchestrator` (coordina los 3 motores)
- `core/webhook_server.py` — Servidor HTTP para recibir alertas de TradingView
- `core/telegram_bot.py` — Bot de Telegram para monitoreo y control
- `core/data_feed.py` — Feed de datos de mercado
- `core/state_manager.py` — Persistencia de estado (Supabase)
- `core/indicators.py` — Indicadores técnicos nativos (sin pandas-ta)
- `exchange_connector.py` — Conexión a Binance Futures (hedge mode)

### Infraestructura
- **Deploy:** Railway (auto-deploy desde branch `main` en GitHub)
- **Alertas:** TradingView → Webhook → Bot → Binance
- **Monitoreo:** Bot de Telegram con comandos completos
- **Estado:** Supabase para persistencia

---

## 📝 Historial de Cambios (cronológicamente)

### Fase 1: Despliegue Inicial
**Commits:** `16d00f7` → `16ea5d2`

- ✅ Arquitectura unificada Railway (B1+B2+B3 en un solo proceso)
- ✅ Múltiples fixes de compatibilidad Python/Railway:
  - Pin Python 3.10, resolver pandas-ta
  - Reemplazar pandas-ta por indicadores nativos (sin dependencias externas)
  - Credenciales con fallback loop para evitar crash en startup
  - Root shim (`requirements.txt` + `Procfile`) para deploy desde subdirectorio
- ✅ Región optimizada: Singapore (baja latencia a Binance)

---

### Fase 2: Bot de Telegram
**Commits:** `85cf4fe` → `912ca4c`

Implementación completa del bot de Telegram para monitoreo:

| Comando | Función |
|---------|---------|
| `/start`, `/help` | Inicio y ayuda |
| `/balance` | Balance actual en Binance |
| `/positions` | Posiciones abiertas con etiqueta de motor (B1/B2/B3) |
| `/report` | Reporte completo del estado del sistema |
| `/metrics`, `/pnl`, `/sharpe` | Métricas de rendimiento |
| `/risk` | Análisis de riesgo (incluye kill switch B2 del -12%) |

**Fixes asociados:**
- `getattr` para engine state
- Corrección de dict keys en monitor loop
- Fix `await` en llamada sync `get_balance`
- Fix initial capital en reporte

---

### Fase 3: Asignación de Pares y Hedge Mode
**Commits:** `a75b3dc` → `8d8e8ae`

- ✅ **Hedge Mode** compatible en B1 y B2 (posiciones LONG y SHORT simultáneas)
- ✅ Lógica async corregida en motor B2
- ✅ Atribución correcta de posiciones por motor en Telegram
- ✅ **Prioridad de pares por motor:**
  - SOLUSDT → siempre B1
  - DOTUSDT, AVAXUSDT → siempre B2
- ✅ **Auto-sync** de posiciones existentes al iniciar B2

---

### Fase 4: Integración TradingView Webhooks
**Commits:** `b6ba1f1` → `c574584`

- ✅ Servidor webhook para recibir alertas de TradingView (B1, B2, B3)
- ✅ Unificación de variables de entorno (`TELEGRAM_BOT_TOKEN`, `SUPABASE_ANON_KEY`)
- ✅ Hardening de `.gitignore` para proteger secretos
- ✅ Fix de imports faltantes y bugs lógicos de B1

---

### Fase 5: Corrección de Ejecución de Trades (23 Feb 2026)
**Commits:** `f201aa6` → `325fbba`

Refactorización mayor del sistema webhook y corrección de 4 bugs críticos:

| Capa | Problema | Solución |
|------|----------|----------|
| **Webhook** | Bloqueaba respuesta a TradingView | Fire-and-Forget (`asyncio.create_task`), respuesta en ~10ms |
| **API** | B2 llamaba `create_order()` inexistente | Delegado a `_execute_trade()` |
| **Estado** | Webhooks bloqueados si engine no estaba "Running" | Eliminado state check para señales externas |
| **Tipo** | `float(None)` crash cuando TradingView no enviaba precio | Fallback `or 0` + auto-fetch desde ticker |
| **Precisión** | Binance error `-1111` (demasiados decimales) | Mapa `QTY_PRECISION` + `math.floor` rounding |

**Mejoras adicionales:**
- Reintentos con backoff exponencial para errores Binance 429/500
- Health endpoint con `webhooks_received`, `webhooks_success`, `webhooks_errors`
- Diagnóstico `last_error` en respuesta de health

---

### Fase 6: Comandos de Cierre por Telegram (23 Feb 2026)
**Commit:** `be7a1d5`

- ✅ Comandos `/close_b1`, `/close_b2`, `/close_b3` para cerrar posiciones individuales
- ✅ Script `close_all.py` para cierre masivo desde terminal

---

### Fase 7: Estrategias Bear/Bull Market (27 Feb 2026)
**Commit:** `5c7d093`

Upgrade para que los 3 motores detecten y se adapten a mercados alcistas/bajistas:

#### B1 Sprint — Sesgo Macro
- Nuevo: EMA 200 en 1H para determinar macro bias
- Bull (precio > EMA200 1H): Señales LONG +0.10, SHORT -0.10
- Bear (precio < EMA200 1H): Señales SHORT +0.10, LONG -0.10
- **Archivos:** `engines/b1_sprint/strategy.py`, `engines/b1_sprint/engine.py`

#### B2 Resilience — Parámetros Duales

| Parámetro | Bull | Bear |
|-----------|------|------|
| SL ATR mult | 2.0x | 1.5x |
| TP ATR mult | 4.0x | 3.0x |
| RSI Long | 40-70 | 45-65 |
| RSI Short | 30-60 | 25-55 |
| Min strength | 0.55 | 0.60 |
| Max leverage | 5x | 4x |

- **Archivos:** `engines/b2_resilience/strategy.py`, `engines/b2_resilience/engine.py`

#### B3 Anchor — Estrategia Dual Completa
- 🟢 **Bull:** Golden Cross (EMA50 > EMA200 4H) → LONG, SL 3.0x ATR, TP 6.0x ATR
- 🔴 **Bear:** Death Cross (EMA50 < EMA200 4H) → SHORT, SL 2.5x ATR, TP 5.0x ATR
- Antes: B3 no operaba en bear market (retornaba `None`)
- **Archivos:** `engines/b3_anchor/strategy.py`, `engines/b3_anchor/engine.py`

#### Pine Scripts para TradingView (backtesting)
- `tradingview/B1_Sprint_BearBull_V6.pine`
- `tradingview/B2_Resilience_BearBull_V7.pine`
- `tradingview/B3_Anchor_BearBull_V7.pine`

---

### Fase 8: Comando /tendencia (27 Feb 2026)
**Commits:** `deb881d`, `fbcaeb4`

- ✅ Nuevo comando `/tendencia` en Telegram
- Análisis multi-indicador Bull/Bear en tiempo real
- Fix de uso de `connector` vs `exchange` en bot de Telegram

---

## 🔧 Configuración y Variables de Entorno

Las credenciales se manejan en `.env.testnet` (local) y en Railway (producción):

```
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
BINANCE_TESTNET=true

TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

SUPABASE_URL=...
SUPABASE_ANON_KEY=...

TRADINGVIEW_WEBHOOK_SECRET=...
```

---

## 📂 Estructura del Proyecto

```
Bot Crypto/
├── Bot Crypto/
│   ├── main.py                    # Orquestador principal
│   ├── exchange_connector.py      # Conector Binance Futures
│   ├── core/
│   │   ├── data_feed.py           # Feed de datos
│   │   ├── indicators.py          # Indicadores nativos
│   │   ├── state_manager.py       # Persistencia Supabase
│   │   ├── telegram_bot.py        # Bot Telegram (31KB)
│   │   └── webhook_server.py      # Servidor HTTP webhooks
│   ├── engines/
│   │   ├── b1_sprint/             # Motor scalping
│   │   │   ├── engine.py
│   │   │   └── strategy.py
│   │   ├── b2_resilience/         # Motor swing
│   │   │   ├── engine.py
│   │   │   └── strategy.py
│   │   └── b3_anchor/             # Motor largo plazo
│   │       ├── engine.py
│   │       └── strategy.py
│   ├── safety/                    # Kill switches
│   ├── backtest_*.py              # Scripts de backtesting
│   ├── close_all.py               # Cierre masivo
│   └── *.docx / *.pdf             # Documentación técnica
├── tradingview/
│   ├── B1_Sprint_BearBull_V6.pine
│   ├── B2_Resilience_BearBull_V7.pine
│   └── B3_Anchor_BearBull_V7.pine
├── requirements.txt               # Root shim → Railway
├── Procfile                       # cd Bot\ Crypto && python main.py
└── .gitignore
```

---

## 🚀 Cómo Retomar el Proyecto

1. **Clonar el repo:** `git clone <url-del-repo>`
2. **Instalar deps:** `pip install -r requirements.txt` (desde la raíz)
3. **Configurar `.env.testnet`** con las credenciales de Binance y Telegram
4. **Ejecutar local:** `cd "Bot Crypto" && python main.py`
5. **Deploy:** Push a `main` → Railway auto-deploys

### Tareas Pendientes
- [ ] Validar Pine Scripts en TradingView Strategy Tester (bear market)
- [ ] Monitorear señales post-deploy de estrategias Bear/Bull
- [ ] Evaluar resultados de backtesting con parámetros duales
