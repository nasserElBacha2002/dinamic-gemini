# Estructura recomendada del frontend React (V3.0)

## Ubicación en el repositorio

**Monorepo:** el frontend vive en una carpeta propia en la raíz del repo, sin mezclar con el backend Python.

```
dinamic-gemini/
├── src/                    # Backend Python (existente)
├── tests/
├── docs/
├── frontend/               # ← App React (nueva)
│   ├── public/
│   ├── src/
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── pyproject.toml
└── ...
```

**Por qué `frontend/` y no `web/` o `client/`:** nombre corto, estándar en muchos monorepos y deja claro que es la capa de presentación que consume la API.

---

## Stack (según V3.0 y reglas de estilo)

- **React 18** + **TypeScript**
- **Vite** como bundler (rápido, ESM, buena DX)
- **Material UI (MUI)** como librería de UI
- **React Router** para rutas
- **TanStack Query** para datos remotos y caché
- **MUI Data Grid** para tablas operativas complejas (posiciones, inventarios, pasillos, productos, historial de revisión). Para tablas muy simples puede usarse el componente `Table` de MUI; para listas con filtros, ordenación y paginación el estándar es **MUI Data Grid**.

No añadir Tailwind, CSS Modules globales ni otra librería de estilos sin justificación; MUI + `sx` + `theme` es la base. La ubicación canónica del frontend es **`frontend/`** en la raíz del repositorio.

---

## Estructura de carpetas dentro de `frontend/src/`

```
frontend/src/
├── api/                    # Cliente HTTP y funciones por recurso
│   ├── client.ts           # Axios/fetch base, baseURL, interceptors
│   ├── inventories.ts      # GET/POST inventarios
│   ├── aisles.ts            # Pasillos por inventario
│   ├── jobs.ts              # Crear job, estado (si se expone)
│   └── entities.ts          # Posiciones/pallets, correcciones
│
├── components/             # Componentes reutilizables
│   ├── layout/              # Layout principal, sidebar, header
│   │   ├── AppLayout.tsx
│   │   └── MainNav.tsx
│   ├── common/              # Botones, chips, loaders, alerts
│   │   ├── LoadingState.tsx
│   │   └── ErrorAlert.tsx
│   └── entities/            # Componentes de dominio (opcional agrupar aquí)
│       └── EntityTable.tsx
│
├── features/               # Por pantalla/caso de uso (opcional pero escalable)
│   ├── inventories/        # Lista + crear inventario
│   │   ├── InventoryList.tsx
│   │   └── CreateInventoryDialog.tsx
│   ├── aisles/             # Pasillos, carga de evidencia
│   │   ├── AisleList.tsx
│   │   ├── UploadEvidence.tsx
│   │   └── AisleResultsTable.tsx
│   └── entity-detail/      # Detalle posición, correcciones
│       └── EntityDetailView.tsx
│
├── hooks/                  # Hooks reutilizables
│   ├── useInventories.ts   # TanStack Query para inventarios
│   ├── useAisles.ts
│   └── useEntityDetail.ts
│
├── pages/                  # Páginas por ruta (contenedores que usan features + layout)
│   ├── InventoryListPage.tsx
│   ├── InventoryDetailPage.tsx
│   ├── AisleUploadPage.tsx
│   ├── AisleResultsPage.tsx
│   └── EntityDetailPage.tsx
│
├── theme/                  # MUI theme (tokens, tipografía, componentes base)
│   ├── theme.ts
│   └── palette.ts
│
├── types/                  # Tipos TS alineados con la API
│   ├── inventory.ts
│   ├── aisle.ts
│   └── entity.ts
│
├── App.tsx
├── main.tsx
└── routes.tsx              # Definición de rutas (React Router)
```

---

## Criterios de organización

1. **`api/`**  
   Un solo cliente configurado (base URL desde env), y un archivo por recurso (inventories, aisles, entities) para mantener las llamadas centralizadas y fáciles de mockear en tests.

2. **`pages/` vs `features/`**  
   - **pages:** contenedores por URL; montan layout y deciden qué feature(s) mostrar.  
   - **features:** lógica y UI por caso de uso (lista de inventarios, carga de pasillo, tabla de resultados). Así se puede reutilizar o testear por bloque.

3. **`hooks/`**  
   Encapsulan TanStack Query (y quizá estado local) por recurso o pantalla. Las páginas/features consumen estos hooks en lugar de llamar a la API directamente.

4. **`theme/`**  
   Un único theme de MUI (y si hace falta, archivos de paleta/tipografía) para cumplir con la regla de estilos V3: MUI como base, `sx` para ajustes locales, theme para tokens globales.

5. **`types/`**  
   Tipos compartidos que reflejan los DTOs de la API; evita “any” y documenta el contrato frontend–backend.

---

## Variables de entorno del frontend

Crear `frontend/.env.example` y `frontend/.env.local` (este último en `.gitignore`):

```bash
# API del backend (desarrollo local)
VITE_API_BASE_URL=http://localhost:8000
```

En código: `import.meta.env.VITE_API_BASE_URL`. El backend ya expone rutas bajo `/api/`; el cliente en `api/client.ts` usará esta base.

---

## Comandos típicos

Desde la raíz del repo:

```bash
cd frontend
npm install
npm run dev          # Desarrollo (proxy o CORS al backend)
npm run build        # Build de producción
npm run preview      # Preview del build
```

En CI/CD: instalar dependencias del frontend, build, y servir los estáticos desde el mismo dominio que la API o desde un servidor web (nginx, etc.).

---

## Resumen

| Aspecto        | Recomendación                                      |
|----------------|----------------------------------------------------|
| Ubicación      | **`frontend/`** en la raíz del repo (única ubicación oficial del frontend). |
| Generador      | Vite + template `react-ts`                        |
| UI             | Material UI + `sx` + theme                        |
| Tablas complejas | MUI Data Grid para vistas operativas             |
| Datos          | TanStack Query; cliente en `api/`                  |
| Rutas          | React Router; definición en `routes.tsx`          |
| Estructura     | `api/`, `components/`, `features/`, `pages/`, `hooks/`, `theme/`, `types/` |
| Env            | `VITE_API_BASE_URL` para la URL base del backend  |

Con esta estructura se puede implementar las pantallas mínimas de la Fase 6 (inventarios, pasillos, carga, resultados, detalle de posición) sin refactor grande después, y manteniendo una sola fuente de verdad para estilos (MUI) según el documento de reglas de estilo del frontend V3.

---

## Consideraciones de deployment (monorepo)

Meter el frontend en `frontend/` dentro del mismo repo **no tiene por qué complicar el deploy** si se define un flujo claro. Lo que sí hay que tener en cuenta:

### Posibles complicaciones

| Riesgo | Causa | Mitigación |
|--------|--------|------------|
| **Dos pasos de build** | Backend (Python) y frontend (Node) con dependencias y comandos distintos | En CI: dos jobs o dos steps (ej. `pip install` + `npm ci` en `frontend/`). No mezclar en el mismo entorno si no usas imagen multi-stage. |
| **URL de la API en producción** | El frontend compila `VITE_API_BASE_URL` en build time | Definir la variable en el entorno de build (CI) o en un `.env.production` no versionado. Nunca hardcodear la URL de prod. |
| **Dónde sirves los estáticos** | Backend y frontend pueden ir al mismo dominio o a dominios distintos | Decidir un solo patrón: mismo origen (backend sirve `dist/`) o front en CDN/host estático y CORS bien configurado en el backend. |
| **CORS** | Si front y API están en distintos dominios | Configurar CORS en la API (FastAPI/Flask) para el origen del frontend en cada entorno. |
| **Secretos y env** | Backend usa `.env`; frontend usa `VITE_*` (públicos) | No poner secretos en `VITE_*` (se embeben en el bundle). Solo URL base y flags públicos. Secretos solo en backend. |

### Patrones de deploy recomendados

**A) Un solo servicio (más simple al principio)**  
- En CI: build del frontend (`cd frontend && npm ci && npm run build`).  
- El backend sirve los estáticos desde una ruta (ej. `/` o `/app`) leyendo los archivos de `frontend/dist/` (copiados en el artefacto o en la imagen).  
- Un solo despliegue, un solo dominio: sin CORS. La API sigue en `/api/`.  
- **Ventaja:** un único deploy, un único origen. **Desventaja:** cada cambio de front obliga a redesplegar el backend si comparten imagen.

**B) Frontend y backend separados**  
- Frontend: build → subir `frontend/dist/` a un CDN o a un host estático (Vercel, Netlify, S3 + CloudFront, etc.).  
- Backend: deploy como siempre (servidor, contenedor, serverless).  
- En build del frontend se inyecta `VITE_API_BASE_URL` con la URL pública de la API.  
- CORS en la API permitiendo el origen del frontend.  
- **Ventaja:** escalado y caché del front independientes. **Desventaja:** dos pipelines y configurar CORS bien.

### CI/CD (resumen)

- **Backend:** `pip install`, tests (pytest), y el artefacto/servicio que ya uses.  
- **Frontend:** `cd frontend && npm ci && npm run build` (y opcionalmente tests/lint). El artefacto es `frontend/dist/`.  
- Si usas **Docker:** una imagen puede tener solo el backend y copiar `frontend/dist` en un multi-stage (build Node en una etapa, copiar `dist` a la imagen final con Python). Así un solo contenedor sirve API + estáticos.

### .gitignore

Cuando exista `frontend/`, conviene ignorar dependencias y build del frontend en la raíz:

```gitignore
# Frontend
frontend/node_modules/
frontend/dist/
frontend/.env.local
frontend/.env.*.local
```

Así el repo no sube `node_modules` ni el bundle generado; el deploy los genera en CI o en la imagen Docker.

### Conclusión

El monorepo con `frontend/` **no complica el deploy** si:  
1) en CI tienes un step/job explícito para instalar y buildear el frontend,  
2) defines una sola forma de servir el front (mismo servidor que la API o CDN + CORS), y  
3) usas variables de entorno de build (`VITE_API_BASE_URL`) y no mezclas secretos en el bundle del frontend. Definir esto al inicio evita sorpresas en producción.
