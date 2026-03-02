---
description: Leer el resumen completo del proyecto Bot Crypto para retomar el trabajo desde otro computador
---

# Contexto del Proyecto Bot Crypto

Este workflow carga el contexto completo del proyecto para que puedas retomarlo sin perder información.

## Pasos

1. Lee el archivo de changelog completo del proyecto:

```
view_file "Bot Crypto/PROJECT_CHANGELOG.md"
```

2. Revisa el estado actual del repositorio (último commit, branch, etc.):

```
git log --oneline -5
```

3. Revisa si hay posiciones abiertas o estado del bot revisando los archivos de entorno:

```
view_file "Bot Crypto/.env.testnet"
```

4. Resume al usuario:
   - Qué es el proyecto (sistema de trading con 3 motores: B1, B2, B3)
   - Cuáles fueron las últimas actualizaciones
   - Qué tareas quedan pendientes
   - El estado actual de la configuración
