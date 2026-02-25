# 🎯 Guía de Uso Óptimo - Evitar Duplicados y Reducir Costos

## ⚠️ Problema Común: Demasiados Frames Similares

Cuando un video tiene un **paneo lento** sobre un pallet, extraer frames a 1 FPS puede generar **10-20 frames casi idénticos**. Esto causa:

1. **Riesgo de doble conteo** - Gemini puede confundir el mismo pallet visto desde diferentes ángulos
2. **Costos disparados** - Pagas por procesar la misma información visual múltiples veces

## ✅ Soluciones Implementadas

### 1. **Reducir el FPS de Extracción**

Para videos con paneo lento, usa un FPS más bajo:

```bash
# ❌ MAL: 1 FPS puede generar 10 frames similares
python test_video_frames.py video.mp4 --fps 1.0

# ✅ BIEN: 0.2 FPS (1 frame cada 5 segundos) = 2-3 frames únicos
python test_video_frames.py video.mp4 --fps 0.2
```

**Recomendaciones por tipo de video:**
- **Paneo lento sobre pallet estático:** `--fps 0.2` (1 frame cada 5 segundos)
- **Cámara fija con movimiento:** `--fps 0.5` (1 frame cada 2 segundos)
- **Cámara en movimiento rápido:** `--fps 1.0` (1 frame por segundo)

### 2. **Filtrar Frames Similares Automáticamente**

Usa el filtro de similitud para descartar duplicados **antes** de enviar a la API:

```bash
# Activa el filtro de similitud (threshold: 0.95 = 95% similar = descartar)
python test_video_frames.py video.mp4 --filter-similar

# Ajusta el threshold si es necesario (más estricto = menos frames)
python test_video_frames.py video.mp4 --filter-similar --similarity-threshold 0.90
```

**Cómo funciona:**
- Compara cada frame con el anterior usando histogramas
- Si la similitud es > 95%, descarta el frame
- Solo envía frames únicos a la API
- **Ahorra costos automáticamente**

### 3. **Usar Estrategia "distributed"**

La estrategia `distributed` incluye primer y último frame, ideal para paneos:

```bash
python test_video_frames.py video.mp4 \
  --fps 0.2 \
  --strategy distributed \
  --filter-similar
```

## 📊 Ejemplo Práctico

### Antes (❌ Problema):
```bash
python test_video_frames.py video.mp4 --fps 1.0 --max-frames 10
# Resultado: 10 frames casi idénticos
# Costo: 10 llamadas a API
# Riesgo: Doble conteo alto
```

### Después (✅ Optimizado):
```bash
python test_video_frames.py video.mp4 \
  --fps 0.2 \
  --max-frames 5 \
  --strategy distributed \
  --filter-similar \
  --similarity-threshold 0.95
# Resultado: 2-3 frames únicos
# Costo: 2-3 llamadas a API (70% ahorro)
# Riesgo: Doble conteo bajo
```

## 🔧 Configuración Recomendada por Escenario

### Escenario 1: Paneo Lento sobre Pallet Estático
```bash
python test_video_frames.py video.mp4 \
  --fps 0.2 \
  --max-frames 3 \
  --strategy distributed \
  --filter-similar
```

### Escenario 2: Cámara Fija, Múltiples Pallets
```bash
python test_video_frames.py video.mp4 \
  --fps 0.5 \
  --max-frames 10 \
  --strategy uniform \
  --filter-similar
```

### Escenario 3: Cámara en Movimiento Rápido
```bash
python test_video_frames.py video.mp4 \
  --fps 1.0 \
  --max-frames 15 \
  --strategy uniform \
  --filter-similar \
  --similarity-threshold 0.90
```

## 💡 Tips Adicionales

1. **Prueba primero con `--no-save`** para ver cuántos frames se extraerían:
   ```bash
   python test_video_frames.py video.mp4 --fps 0.2 --no-save
   ```

2. **Ajusta el threshold según tu video:**
   - Videos con mucho movimiento: `--similarity-threshold 0.90`
   - Videos con paneo muy lento: `--similarity-threshold 0.95`

3. **Usa la consolidación MAD** (ya implementada en Fase 6):
   - Procesa frames individualmente
   - La mediana estadística combinará resultados
   - No necesitas enviar frames juntos en un batch

## 📈 Ahorro de Costos Estimado

| Configuración | Frames Extraídos | Frames Únicos | Ahorro |
|--------------|------------------|---------------|--------|
| Sin optimización | 10 | 10 | 0% |
| FPS 0.2 | 3 | 3 | 70% |
| FPS 0.2 + Filtro | 3 | 2 | 80% |

## 🎯 Recordatorio Importante

**El sistema está diseñado para procesar frames individualmente:**
- Cada frame se envía por separado a Gemini
- Los resultados se consolidan con MAD (Median Absolute Deviation)
- No necesitas enviar frames juntos en un batch
- La consolidación matemática elimina variaciones naturales

---

**Última actualización:** Después de Fase 4
