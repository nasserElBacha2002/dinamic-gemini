# Auditoría frontend - componentes reutilizables

## Resumen

- Archivos en zonas candidatas a reutilizacion (components/pages/views/features): 0
- El objetivo es detectar repeticion visual o de logica para consolidar componentes.

## Componentes detectados

- Referencias a Button: 332
- Referencias a Card: 154
- Referencias a Dialog/Modal: 283
- Referencias a Table/DataGrid: 341
- Referencias a TextField: 23
- Referencias a Loading/CircularProgress: 295
- Referencias a Alert/Snackbar/ErrorState/Empty: 302

## Patrones repetidos a revisar

- Construcciones repetidas de tablas y filtros en modulos de resultados/revision.
- Dialogs con estructura similar que podrian compartir base comun.
- Estados de loading/empty/error potencialmente dispersos en multiples pantallas.

## Posibles candidatos a componente genérico

- Contenedores de estado de datos: loading/empty/error.
- Dialogs base con layout, acciones y comportamiento estandar.
- Toolbars de filtros y tablas con paginacion/orden reutilizables.

## Recomendaciones futuras

- Crear inventario de componentes por dominio antes de consolidar.
- Definir criterios de extraccion (repeticion, acoplamiento, estabilidad).
- Validar manualmente hallazgos; este reporte usa conteo por patrones de texto.
