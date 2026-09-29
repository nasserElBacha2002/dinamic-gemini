# Raspberry scanner local (V1)

Módulo aislado para una Raspberry Pi que publica una página local, recibe
lecturas RAW de un scanner serial y mantiene un snapshot local de configuración
de reconocimiento por cliente/proveedor. Antes de escanear se seleccionan cliente
y proveedor (o **Todos**) exclusivamente desde ese snapshot local.

## Decisiones y alcance

- Servidor Python de biblioteca estándar: no incorpora dependencias del sistema principal.
- El transporte es un dispositivo serial POSIX configurado y líneas terminadas en CR/LF.
  La única transformación es quitar dicho delimitador; por ejemplo, los espacios de
  `" POSITION "` se conservan. No hay reglas `POSITION`, `D1` ni de inventario.
- Polling HTTP cada segundo: es más simple que mantener WebSocket/SSE y se recupera
  solo cuando un cliente se desconecta o vuelve a abrir la página.
- Las últimas 100 lecturas quedan en memoria (configurable). Al reiniciar se pierden.
- La configuración offline sí es persistente: se valida antes de guardarse y se reemplaza
  atómicamente, conservando la última versión válida si el backend no está disponible.

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

   # Fase 1: configuración offline por cliente.
   DINAMIC_CLIENT_ID=<client-id>
   DINAMIC_BACKEND_URL=https://api.example.com
   # Temporal mientras el backend conserve JWT de usuario. No es login de la UI local.
   DINAMIC_BACKEND_BEARER_TOKEN=<token-provisionado>
   # Opcional; systemd ya crea el directorio por StateDirectory.
   DINAMIC_CONFIG_PATH=/var/lib/dinamic-raspberry-scanner/recognition-config.json
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

## Configuración offline y selección (Fases 1 y 2)

El backend expone `GET /api/v3/raspberry/recognition-config`, autenticado con
`X-Device-Token`. La Raspberry no pide usuario/contraseña en su interfaz local y
no almacena ni expone el token dentro del snapshot.

Endpoints locales disponibles:

- `GET /api/config`: estado del snapshot y última sincronización.
- `POST /api/config/sync`: intenta actualizar; ante error conserva last-known-good.
- `GET /api/config/clients`, `GET /api/config/clients/{client_id}` y sus rutas
  `/suppliers`: configuración disponible offline por cliente/proveedor.
- `GET /api/selection` y `POST /api/selection`: selección operacional
  `{ "client_id": "...", "supplier_id": null | "..." }`.

`supplier_id: null` significa **Todos**: conserva el valor RAW y no intenta
perfiles SUPPLIER ni autodetección. No representa DINAMIC. Con un proveedor
específico, ITEM y POSITION se resuelven por separado: `SUPPLIER` aplica el
perfil local determinista; `DINAMIC` usa D1 para ITEM y DINAMIC_POSITION para
POSITION. Estructuras SUPPLIER que el scanner local no puede resolver (por
ejemplo GS1) quedan como no resueltas y no hacen fallback a DINAMIC.

La selección sólo cambia con el scanner detenido; cambiar cliente desde la UI
restablece proveedor a Todos. La selección es deliberadamente efímera.

## Captura y TXT de pasillo (Fase 3)

Ingresá un código de pasillo y usá **Iniciar captura**. La captura congela la
selección actual, conserva únicamente resultados F2 exportables en su orden de
lectura y, al finalizar, escribe `<pasillo>.txt` de forma atómica. El directorio
se configura con `DINAMIC_EXPORT_DIRECTORY` (por defecto,
`/var/lib/dinamic-raspberry-scanner/exports`). Un archivo existente no se
sobrescribe.

El formato sigue el importador existente: ITEM DINAMIC conserva D1 canónico y
POSITION DINAMIC v2 se escribe como `POSITION|label_id|pallet|side`; JSON
`DINAMIC_POSITION` nunca se exporta. Los payloads supplier se conservan RAW
para que el importador los valide con el perfil backend. El TXT no transporta
`supplier_id`: para un pasillo nuevo con más de un proveedor, la resolución
posterior del importador puede resultar ambigua; la Raspberry no inventa un
header ni consulta/crea pasillos remotamente.

La aplicación no sincroniza automáticamente al arrancar en esta fase: una actualización
debe dispararse explícitamente. Esto evita convertir un problema de conectividad o
autorización en una dependencia para iniciar el scanner local.

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
