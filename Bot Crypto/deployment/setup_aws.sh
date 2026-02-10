#!/bin/bash

# ==========================================
# SETUP SCRIPT FOR ANTIGRAVITY B1 V4a (AWS)
# ==========================================

echo "🚀 Iniciando configuración de servidor..."

# 1. Actualizar sistema
echo "📦 Actualizando paquetes del sistema..."
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y build-essential wget python3-dev python-is-python3 python3-pip python3-venv

# 2. Instalar TA-Lib (Requisito crítico)
echo "📚 Instalando TA-Lib (C Core)..."
cd /tmp
wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
tar -xzf ta-lib-0.4.0-src.tar.gz
cd ta-lib/
./configure --prefix=/usr
make
sudo make install
cd ..
rm -rf ta-lib ta-lib-0.4.0-src.tar.gz
echo "✅ TA-Lib instalado."

# 3. Configurar entorno Python
echo "🐍 Configurando entorno virtual Python..."
cd ~/antigravity/Bot\ Crypto  # Asumiendo que esta es la ruta de subida
python3 -m venv venv
source venv/bin/activate

# 4. Instalar dependencias
echo "⬇️ Instalando librerías Python..."
pip install --upgrade pip
pip install -r requirements.txt

# 5. Configurar permisos
echo "🔒 Ajustando permisos..."
chmod +x run_b1_demo.py

echo "=========================================="
echo "🎉 ¡INSTALACIÓN COMPLETADA!"
echo "   Para iniciar manual: source venv/bin/activate && python run_b1_demo.py"
echo "   Para iniciar servicio: sudo systemctl start b1_bot"
echo "=========================================="
