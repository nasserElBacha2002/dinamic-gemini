

# 📦 PLAN DE IMPLEMENTACIÓN — MÓDULO DE INGESTA DE MEDIOS (VERSIÓN FINAL)

---

# 1. 🎯 Objetivo del sistema

Construir un módulo que permita:

> **ingestar fotos (principalmente post-vuelo de dron), organizarlas, revisarlas y convertirlas en SourceAssets para el pipeline**

### Casos soportados

* 🟢 **Modo A** → Upload manual
* 🔵 **Modo B (principal)** → Post-vuelo (descarga → subida)
* ⚪ **Modo C (futuro)** → Integración directa con dron

---

# 2. 🧠 Modelo mental del sistema (simple y clave)

Flujo REAL del usuario:

```plaintext
1. Crear sesión (Import Session)
2. Subir fotos (muchas)
3. Ver y ordenar automáticamente (preview)
4. Ajustar si hace falta
5. Confirmar → materializar
6. Pipeline procesa
```

Internamente:

```plaintext
CaptureSession
 → CaptureSessionItem (staging)
 → preview (determinístico)
 → materialización
 → SourceAsset
```

---

# 3. 🚧 Estado actual (lo que YA está hecho)

Backend:

* ✔ Sessions (CRUD completo)
* ✔ Upload staging
* ✔ Time extraction (EXIF / mtime / fallback)
* ✔ Clock offset
* ✔ Preview determinístico
* ✔ Materialización con idempotencia
* ✔ Invariante: pipeline solo usa `SourceAsset`

👉 Conclusión:

> ❗ **NO hay que tocar el backend core**
> ❗ **El problema es 100% de productización (UI + flujo)**

---

# 4. ⚠️ Principios obligatorios (guardrails)

Estos NO se pueden romper:

* ❌ Nunca procesar desde staging
* ❌ Nunca duplicar assets (idempotencia obligatoria)
* ❌ No permitir acciones inválidas por estado
* ✔ Preview SIEMPRE determinístico
* ✔ Materialización irreversible (conceptualmente)

---

# 5. 🧭 Fases de implementación

---

# 🟣 FASE R1 — Reframing + contratos (rápida pero clave)

## Objetivo

Alinear backend + frontend + producto

---

## 🎫 Tickets

### Backend

**B1 — Inventario de endpoints**

* documentar todos los endpoints `/capture-sessions`

**B2 — Máquina de estados clara**

Estados:

```plaintext
DRAFT
IMPORTING
READY_FOR_REVIEW
ASSIGNMENT_PROPOSED
CONFIRMING
```

**B3 — Matriz de errores**

* mapear errores → UX

---

### Frontend

**F1 — Tipado completo**

* session
* items
* preview
* materialización

---

### Producto

**P1 — Naming**

* UI = “Import Session”

**P2 — Flujo oficial**

```plaintext
IMPORT → PREVIEW → MATERIALIZE
```

---

# 🟢 FASE R2 — Import UI (CRÍTICA)

## Objetivo

👉 Poder subir fotos del dron (muchas)

---

## 🎫 Tickets

### Backend

**B1 — Gap check endpoints**

* validar que no falta nada

---

### Frontend

---

### **F1 — Listado de sesiones**

* tabla de sesiones
* estado
* fecha
* botón “entrar”

---

### **F2 — Crear sesión**

* botón crear
* feedback inmediato

---

### **F3 — Upload masivo (MUY IMPORTANTE)**

```diff
+ drag & drop
+ multi-file upload
+ progreso por archivo
+ errores individuales
```

👉 pensado para 50–300 fotos

---

### **F4 — Detalle de sesión**

Mostrar:

* lista de imágenes
* estado
* tiempo detectado
* confianza

---

### **F5 — Orden visual automático**

```diff
+ ordenar por effective_capture_time
```

---

### **F6 — Guardrails de UI**

```diff
- no permitir upload si cerrada
- no permitir preview si no READY_FOR_REVIEW
```

---

### **F7 — Cerrar sesión**

* botón claro
* cambia estado

---

### Producto

**P1 — UX modo dron**

Texto claro:

> “Subí las fotos capturadas por el dron después del vuelo”

---

### DoD

* puedo subir 100 fotos sin romper UI
* puedo verlas ordenadas
* puedo cerrar sesión

---

# 🔵 FASE R3 — Preview (donde aparece el valor)

## Objetivo

👉 entender qué foto corresponde a qué posición

---

## 🎫 Tickets

### Backend

**B1 — Validar preview completo**

---

### Frontend

---

### **F1 — Ejecutar preview**

* botón “Generar preview”

---

### **F2 — Agrupación clara**

```plaintext
PROPOSED
CONFLICT
UNASSIGNED
```

---

### **F3 — Vista por tiempo**

```diff
+ ordenar por adjusted_capture_time
```

---

### **F4 — Control de offset**

* slider / input
* re-preview

---

### **F5 — Trazabilidad**

Mostrar:

* adjusted_capture_time
* assignment_reason
* position_id

---

### **F6 — Estado no listo**

Mensaje:

> “No hay elementos válidos para materializar”

---

### Producto

**P1 — Mensaje clave**

> “Esto es una sugerencia automática basada en orden temporal”

---

### DoD

* preview entendible
* conflictos visibles
* offset usable

---

# 🟡 FASE R4 — Materialización (momento crítico)

## Objetivo

👉 convertir fotos en assets reales

---

## 🎫 Tickets

### Backend

**B1 — Validación final endpoint**

---

**B2 — Idempotencia**

* misma key → replay
* distinta → error

---

**B3 — Metadata**

Guardar:

```json
{
  capture_session_id,
  capture_session_item_id
}
```

---

### Frontend

---

### **F1 — Botón MATERIALIZAR**

* bloquea doble click
* muestra loading

---

### **F2 — Resultado**

Mostrar:

```plaintext
✔ 120 assets creados
✔ sesión materializada
```

---

### **F3 — Idempotencia UX**

* retry seguro
* mensaje claro

---

### **F4 — Estado bloqueado**

```diff
+ no se puede editar más
```

---

### **F5 — Trazabilidad visual**

```diff
+ item → SourceAsset creado
```

---

### Producto

**P1 — Definición CONFIRMING**

> “Sesión materializada — lista para procesamiento”

---

### DoD

* materialización segura
* no duplicados
* feedback claro

---

# 🟠 FASE R5 — Confirmación (decisión)

## Opciones

### Opción A (recomendada)

👉 Materialización = fin

### Opción B

👉 Paso extra confirmación

---

### Tickets (solo si B)

* endpoint confirm
* UI confirmación
* estado final

---

# ⚫ FASE R6 — Hardening

---

### Backend

* logs
* métricas
* debug tools

---

### Frontend

* panel admin
* errores
* reintentos

---

### Producto

* playbook
* SLA

---

# ⚪ FASE R7 — Dron directo (FUTURO)

---

Separado completamente.

---

# 6. 🎨 UI Roadmap

---

### U1 — Import

✔ upload
✔ listado

### U2 — Preview

✔ agrupación
✔ offset

### U3 — Materialize

✔ ejecutar
✔ resultado

### U4 — Confirm (opcional)

### U5 — Admin

---

# 7. 🚀 Orden real de ejecución

1. R1 (rápido)
2. R2 (clave)
3. R3 (valor real)
4. R4 (cierre)
5. R5 (si aplica)

---

# 8. 🧠 Resultado final

El sistema queda:

```plaintext
Drone → fotos → upload → preview → materialize → pipeline
```

Y lo más importante:

👉 usable en el mundo real
👉 alineado con tu arquitectura
👉 sin reescribir nada


