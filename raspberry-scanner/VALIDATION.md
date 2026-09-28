# Evidencia de validación

Fecha: 2026-09-28 (entorno de desarrollo local, sin Raspberry ni scanner).

## Comandos ejecutados

```text
python3 -m unittest discover -s raspberry-scanner/tests -v
python3 -m py_compile raspberry-scanner/app.py raspberry-scanner/scanner_service.py
bash -n raspberry-scanner/scripts/configure-hotspot-networkmanager.sh
git diff --check
git diff
git diff --stat
git status --short
```

Resultado inicial: los 3 tests unitarios pasaron; esta evidencia se regenera
con `./scripts/generate-review-evidence.sh` antes de cada revisión. El script
deja la salida completa de tests, compilación, Bash, diff efectivo, diffstat y
status en `.review-evidence/`, sin tocar el índice real de Git.

La corrección V1 final protege el escenario `start → stop → start` mientras
una lectura anterior aún está bloqueada: cada inicio usa una generación de
sesión y resultados/errores de la generación cerrada se descartan. Sin ello,
una lectura vieja podía aparecer tras reiniciar el escaneo.

El smoke test HTTP intentó iniciar el servidor en `127.0.0.1:18080`, pero el
sandbox de desarrollo rechazó la apertura de sockets con
`PermissionError: [Errno 1] Operation not permitted`. Por ello no hay una
validación HTTP de proceso real en este entorno.

`git diff` y `git diff --stat` no listan esta carpeta porque, al momento de
generar la evidencia, es nueva y no está indexada; se guardaron respectivamente
en `review-evidence.git-diff.txt` y `review-evidence.git-diff-stat.txt` (vacíos
por esa semántica de Git). `review-evidence.git-status-short.txt` contiene el
estado abreviado observado. No se modificó el índice ni se realizó commit.
