# 🐍 Activación del Entorno Virtual

El entorno virtual (`venv`) ha sido creado. Para activarlo y usar el proyecto:

## macOS / Linux

```bash
source venv/bin/activate
```

## Windows

```bash
venv\Scripts\activate
```

## Después de activar

Una vez activado, verás `(venv)` al inicio de tu prompt. Luego puedes instalar las dependencias:

```bash
pip install -e ".[dev]"
```

## Desactivar el entorno

Cuando termines de trabajar:

```bash
deactivate
```

## Verificar que está activo

```bash
which python  # Debe mostrar la ruta al venv
pip --version # Debe funcionar
```
