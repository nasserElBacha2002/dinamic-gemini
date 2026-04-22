# Capture Session Terminology Layer (Product Mapping)

Este documento define el mapeo de términos para UX/producto sin renombrar entidades backend.

## Principio

- Backend mantiene naming técnico actual (`CaptureSession`, `CaptureSessionItem`, etc.).
- Producto/UI usa naming orientado a operación real de ingestión post-vuelo.

## Mapeo oficial

- `CaptureSession` -> **Import Session** (o Ingestion Session)
- `CaptureSessionItem` -> **Imported Media Item**
- `Materialization` -> **Confirm Import**
- `preview-assignment` -> **Auto Organization Preview**
- `clock_offset_seconds` -> **Clock Offset Adjustment**
- `CONFIRMING` -> **Materialized and Locked**

## Cómo usar este mapeo

- Documentación técnica backend: mantener términos backend.
- UI y copy: usar términos producto.
- QA/UAT: incluir ambos cuando sea necesario para trazabilidad:
  - "Import Session (`CaptureSession`)"
  - "Confirm Import (`materialize`)"

## Fuera de alcance de R1

- No se renombra código, rutas, tablas ni DTOs backend.
- No se crean aliases de API en esta fase.
