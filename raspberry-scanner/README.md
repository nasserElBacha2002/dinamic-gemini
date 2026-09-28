# Raspberry scanner local (V1)

Módulo aislado para una Raspberry Pi que publica una página local y recibe
lecturas RAW de un scanner serial. No se conecta al backend, no persiste,
exporta ni interpreta valores.

## Decisiones y alcance

- Servidor Python de biblioteca estándar: no incorpora dependencias del sistema principal.
- El transporte es un dispositivo serial POSIX configurado y líneas terminadas en CR/LF.
  La única transformación es quitar dicho delimitador; por ejemplo, los espacios de
  `" POSITION "` se conservan. No hay reglas `POSITION`, `D1` ni de inventario.
- Polling HTTP cada segundo: es más simple que mantener WebSocket/SSE y se recupera
  solo cuando un cliente se desconecta o vuelve a abrir la página.
- Las últimas 100 lecturas quedan en memoria (configurable). Al reiniciar se pierden.

## Resultado del relevamiento

Al crear este módulo no había en el repositorio código para Raspberry Pi, un
programa de lectura de scanner, configuración de `/dev/tty*`/baud rate, ni
dependencia serial reutilizable. Sí existe un importador de TXT generado por un
ESP32 dentro de `backend/`, pero contiene procesamiento de inventario y no se
usa aquí. Por eso **no hay puerto ni protocolo predefinidos**: hay que descubrir
el dispositivo físico antes de configurar `SCANNER_DEVICE` y `SCANNER_BAUD_RATE`.

## Ejecutar localmente

Se requiere Python 3.10+ y no hay instalación de paquetes.

```bash
cd raspberry-scanner
cp .env.example .env   # editar solo después de conocer el dispositivo
set -a; source .env; set +a
python3 app.py --host 127.0.0.1
```

Abrí `http://127.0.0.1:8080`. Sin `SCANNER_DEVICE`, la interfaz sirve igual y
muestra `not_configured` al iniciar. Para pruebas de interfaz sin hardware se
puede usar cualquier ruta inexistente: se mostrará `waiting_for_scanner` y el
error de apertura, sin inventar lecturas.

Ejecutar tests sin hardware:

```bash
python3 -m unittest discover -s tests -v
```

## Preparar y ejecutar en Raspberry Pi

1. Copiá esta carpeta a `/opt/dinamic-raspberry-scanner` y creá el usuario de
   servicio `dinamic` si aún no existe.
2. Conectá el scanner y determiná qué interfaz creó el kernel, por ejemplo con
   `ls -l /dev/serial/by-id/` y `dmesg -w`. Preferí una ruta estable bajo
   `/dev/serial/by-id/` antes que asumir `/dev/ttyUSB0`.
3. Confirmá el modo y baud rate con la documentación/lectura física del scanner;
   este repositorio no aporta esos datos. El scanner debe emitir una lectura por
   CR o LF. Creá el archivo de entorno que lee systemd con
   `sudoedit /etc/dinamic-raspberry-scanner.env` (no lleva `export`) y cargá:

   ```ini
   # Reemplazar solo después de identificar el scanner en /dev/serial/by-id/.
   SCANNER_DEVICE=/dev/serial/by-id/usb-REEMPLAZAR
   SCANNER_BAUD_RATE=9600
   SCANNER_PORT=8080
   SCANNER_MAX_READINGS=100
   ```

   `SCANNER_PORT` se aplica porque el unit no fija el puerto por línea de
   comandos. El host del servicio es deliberadamente `0.0.0.0` para que sea
   accesible desde la red local.

4. Asegurá que `dinamic` pueda abrir el dispositivo (en Raspberry Pi OS suele
   ser `sudo usermod -aG dialout dinamic`; luego reiniciá sesión/servicio).
5. Copiá `systemd/dinamic-raspberry-scanner.service` a
   `/etc/systemd/system/`, revisá rutas/usuario y ejecutá:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now dinamic-raspberry-scanner
   sudo systemctl status dinamic-raspberry-scanner
   ```

El servicio reintenta abrir el scanner si no está conectado y tras una lectura
que falle. Detener el escaneo desde la página cierra el dispositivo; iniciar ya
iniciado y detener ya detenido son operaciones seguras.

## Wi-Fi local autónomo

La red es responsabilidad del sistema operativo, no de la aplicación. El script
`scripts/configure-hotspot-networkmanager.sh` prepara un hotspot con
NetworkManager (la opción habitual en Raspberry Pi OS reciente) y DHCP/NAT
mediante `ipv4.method shared`. Requiere ejecución explícita como root y no se
ejecuta durante el arranque de la aplicación:

```bash
cd /opt/dinamic-raspberry-scanner
sudo WIFI_INTERFACE=wlan0 HOTSPOT_NAME=Dinamic-Scanner \
  HOTSPOT_PASSWORD='elegi-una-clave-segura' \
  ./scripts/configure-hotspot-networkmanager.sh
```

Consultá la IP mostrada al final (también `nmcli -g IP4.ADDRESS device show wlan0`)
y abrí `http://ESA_IP:8080` desde un equipo conectado. Si la imagen instalada no
usa NetworkManager, no ejecutes ese script: configurá el hotspot con el gestor de
red propio de esa imagen y conservá el servicio web separado.

## Validación física pendiente

Los tests cubren framing serial sin hardware, concurrencia de inicio/parada,
lecturas RAW y reconexión simulada. Falta validar físicamente
en Raspberry: identificación de dispositivo, baud rate/modo real, permisos de
grupo, reconexión USB y acceso desde un cliente conectado al hotspot.
