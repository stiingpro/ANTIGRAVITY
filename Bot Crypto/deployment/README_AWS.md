# 🚀 GUÍA MAESTRA: Tu Propio VPS en AWS para Antigravity B1 V4a

Esta guía te lleva de la mano absoluta para crear tu "Computadora en la Nube" (VPS) donde vivirá el bot.

---

## 🛑 PASO 0: Prerrequisitos
1.  Tener una cuenta en [AWS Console](https://console.aws.amazon.com/).
2.  Tener tu tarjeta de crédito vinculada (AWS pide esto aunque uses la capa gratuita).

---

## 🏗️ PASO 1: Crear el Servidor (Instancia EC2)

1.  **Inicia sesión** en la Consola de AWS.
2.  **Selecciona la Región** (Arriba a la derecha, junto a tu nombre).
    *   Recomendado: **US East (N. Virginia) us-east-1** (suele ser la más barata y rápida).
3.  En la barra de búsqueda superior, escribe **EC2** y selecciona la primera opción "EC2 Virtual Servers in the Cloud".
4.  En el panel principal (Dashboard), busca el botón naranja **Launch instance** (Lanzar instancia) y haz clic.

### Configuración de la Instancia (Formulario)

Rellena el formulario con estos datos exactos:

1.  **Name and tags (Nombre):**
    *   Escribe: `Antigravity-B1-V4a`
2.  **Application and OS Images (Imagen del Sistema):**
    *   Selecciona: **Ubuntu**
    *   Asegúrate que diga: **Ubuntu Server 24.04 LTS (HVM), SSD Volume Type** (o 22.04 LTS).
    *   Architecture: **64-bit (x86)**.
3.  **Instance Type (Potencia):**
    *   Busca y selecciona: **t2.micro** (Si tienes cuenta nueva, dice "Free tier eligible").
    *   Si no, **t3.micro** es muy barata y potente.
4.  **Key pair (Llave de acceso) - ¡MUY IMPORTANTE!:**
    *   Haz clic en **Create new key pair**.
    *   **Key pair name:** `antigravity-key`
    *   **Key pair type:** RSA
    *   **Private key file format:** `.pem`
    *   Haz clic en **Create key pair**.
    *   🚨 **SE DESCARGARÁ UN ARCHIVO `.pem`. GUÁRDALO EN UNA CARPETA SEGURA EN TU PC Y NO LO PIERDAS JAMÁS.** (Sugerencia: Muévelo a `d:\ANTIGRAVITY\Bot Crypto\`).
5.  **Network settings (Red):**
    *   Selecciona: **Create security group**.
    *   Marca la casilla: **Allow SSH traffic from** -> Selecciona **Anywhere (0.0.0.0/0)**.
6.  **Configure storage (Disco):**
    *   Cambia **8 GiB** por **15 GiB** (gp3 o gp2) para tener espacio de sobra.

### Lanzamiento
1.  Revisa el resumen a la derecha.
2.  Haz clic en el botón naranja **Launch instance**.
3.  Si sale verde ("Success"), haz clic en **View all instances**.

### Obtener tu IP Pública
1.  Verás tu nueva instancia en la lista. Espera a que "Instance state" diga **Running** (verde).
2.  Selecciona la instancia (casilla azul a la izquierda).
3.  Abajo, busca **Public IPv4 address**. Copia ese número (ej: `54.123.45.67`). Esa es la dirección de tu VPS.

---

## 🔌 PASO 2: Conectarse (Desde tu PC con Windows)

1.  Abre una terminal **PowerShell** o **CMD**.
2.  Navega a la carpeta donde guardaste el archivo `.pem`.
    ```powershell
    cd "d:\ANTIGRAVITY\Bot Crypto"
    ```
3.  Ejecuta el comando de conexión (reemplaza `TU_IP` por la que copiaste):
    ```powershell
    ssh -i "antigravity-key.pem" ubuntu@54.123.45.67
    ```
4.  Si te pregunta `Are you sure you want to continue connecting (yes/no)?`, escribe `yes`.
5.  ¡Listo! Si ves algo como `ubuntu@ip-172-31...:~$`, ya estás DENTRO de tu servidor en AWS. 🎉

---

## 📤 PASO 3: Subir los Archivos del Bot

Necesitamos enviar el código de tu PC al servidor.
1.  Abre **OTRA** ventana de PowerShell en tu PC (no cierres la que está conectada).
2.  Ejecuta este comando (reemplaza `TU_IP`):
    ```powershell
    scp -i "d:\ANTIGRAVITY\Bot Crypto\antigravity-key.pem" -r "d:\ANTIGRAVITY\Bot Crypto" ubuntu@54.123.45.67:~/antigravity
    ```
    *(Esto copiará toda la carpeta `Bot Crypto` dentro de una nueva carpeta `antigravity` en el servidor).*

---

## ⚙️ PASO 4: Instalación Automática (En el Servidor)

Vuelve a la terminal donde estás conectado por SSH (la del PASO 2) y ejecuta:

1.  Entra a la carpeta:
    ```bash
    cd ~/antigravity/Bot\ Crypto
    ```
2.  Dale permisos al instalador y ejecútalo:
    ```bash
    chmod +x deployment/setup_aws.sh
    ./deployment/setup_aws.sh
    ```
    *(Verás muchas letras blancas subiendo. Es normal. Espera a que termine).*

---

## 🔑 PASO 5: Configurar tus Claves Reales

Ahora pondremos tus API Keys de Binance **Mainnet**.
1.  Edita el archivo de producción:
    ```bash
    nano .env.production
    ```
2.  Borra lo que haya y pega esto (rellenando tus datos):
    ```ini
    B1_API_KEY=pon_tu_api_key_aqui
    B1_API_SECRET=pon_tu_secret_key_aqui
    ```
    *(Para guardar en nano: Presiona `Ctrl+O`, luego `Enter`, luego `Ctrl+X`).*

---

## 🚀 PASO 6: ¡Activar el Bot 24/7!

Para que el bot funcione siempre, incluso si cierras la ventana:

```bash
# Copiar configuración de servicio
sudo cp deployment/b1_bot.service /etc/systemd/system/

# Recargar sistema
sudo systemctl daemon-reload

# Encender el bot
sudo systemctl enable b1_bot
sudo systemctl start b1_bot
```

**¡FELICIDADES! Tu bot B1 V4a está vivo en la nube.** ☁️🤖

### Comandos de Control (Monitor)
Para ver qué está haciendo el bot en tiempo real:
```bash
journalctl -u b1_bot -f
```
*(Para salir del monitor: `Ctrl+C`)*
