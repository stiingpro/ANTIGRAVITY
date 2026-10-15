@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo ============================================================================
echo   INICIANDO DEMO EN VIVO 24/7 BINANCE FUTURES - ARQUITECTURA TRIFECTA 2026
echo   Motores: B1 (Range Grid V8) + B2 (Rel Strength V8) + B3 (Wyckoff Vault V8)
echo   Escaneo automatico cada 5 minutos (300 segundos).
echo ============================================================================
py demo_trifecta_2026.py --loop --interval 300
pause
