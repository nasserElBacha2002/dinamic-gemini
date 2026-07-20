import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Box,
  IconButton,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import CropFreeIcon from '@mui/icons-material/CropFree';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import PanToolIcon from '@mui/icons-material/PanTool';
import RemoveIcon from '@mui/icons-material/Remove';
import ZoomInIcon from '@mui/icons-material/ZoomIn';
import ZoomOutIcon from '@mui/icons-material/ZoomOut';
import { useTranslation } from 'react-i18next';
import {
  computeImageLayout,
  displayToNormalized,
  normalizedToDisplay,
  polygonToSvgPoints,
  rectangleToNormalizedPolygon,
  roundNormalizedPolygon,
  type ImageLayout,
} from '../utils/annotationPolygonUtils';

export type AnnotationDrawMode = 'select' | 'rectangle' | 'polygon';

export interface ReferenceAnnotationCanvasItem {
  key: string;
  field_key: string;
  anchor_texts: string[];
  normalized_polygon: number[][] | null;
}

export interface ReferenceAnnotationCanvasProps {
  imageSrc: string | null;
  imageAlt: string;
  items: ReferenceAnnotationCanvasItem[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
  onPolygonChange: (key: string, polygon: number[][] | null) => void;
  drawMode: AnnotationDrawMode;
  onDrawModeChange: (mode: AnnotationDrawMode) => void;
  zoom: number;
  onZoomChange: (zoom: number) => void;
}

const REGION_COLORS = ['#1976d2', '#ed6c02', '#2e7d32', '#9c27b0', '#d32f2f', '#0288d1'];
const MIN_ZOOM = 0.5;
const MAX_ZOOM = 3;
const ZOOM_STEP = 0.25;

function regionColor(index: number): string {
  return REGION_COLORS[index % REGION_COLORS.length];
}

function pointerPosition(
  event: React.PointerEvent<SVGElement | HTMLDivElement>,
  container: HTMLElement
): [number, number] {
  const rect = container.getBoundingClientRect();
  return [event.clientX - rect.left, event.clientY - rect.top];
}

function labelForItem(item: ReferenceAnnotationCanvasItem): string {
  const field = item.field_key.trim();
  const anchors = item.anchor_texts.filter(Boolean).join(', ');
  if (field && anchors) return `${field} · ${anchors}`;
  return field || anchors || '—';
}

export default function ReferenceAnnotationCanvas({
  imageSrc,
  imageAlt,
  items,
  selectedKey,
  onSelect,
  onPolygonChange,
  drawMode,
  onDrawModeChange,
  zoom,
  onZoomChange,
}: ReferenceAnnotationCanvasProps) {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });
  const [naturalSize, setNaturalSize] = useState({ width: 0, height: 0 });
  const [draftRect, setDraftRect] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(
    null
  );
  const [draftPolygon, setDraftPolygon] = useState<number[][]>([]);
  const [draggingVertex, setDraggingVertex] = useState<{ key: string; index: number } | null>(null);

  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;

    const updateSize = () => {
      setContainerSize({
        width: node.clientWidth,
        height: node.clientHeight,
      });
    };
    updateSize();

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', updateSize);
      return () => window.removeEventListener('resize', updateSize);
    }

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      setContainerSize({
        width: entry.contentRect.width,
        height: entry.contentRect.height,
      });
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const layout = useMemo(
    () => computeImageLayout(containerSize.width, containerSize.height, naturalSize.width, naturalSize.height),
    [containerSize.height, containerSize.width, naturalSize.height, naturalSize.width]
  );

  const resetDraft = useCallback(() => {
    setDraftRect(null);
    setDraftPolygon([]);
  }, []);

  useEffect(() => {
    resetDraft();
  }, [drawMode, resetDraft, selectedKey]);

  const handleImageLoad = useCallback(() => {
    const img = imageRef.current;
    if (!img) return;
    setNaturalSize({ width: img.naturalWidth, height: img.naturalHeight });
  }, []);

  const commitPolygon = useCallback(
    (key: string, polygon: number[][]) => {
      onPolygonChange(key, roundNormalizedPolygon(polygon));
      resetDraft();
      onDrawModeChange('select');
    },
    [onDrawModeChange, onPolygonChange, resetDraft]
  );

  const handlePointerDown = useCallback(
    (event: React.PointerEvent<SVGSVGElement>) => {
      if (!selectedKey || !containerRef.current) return;
      const [x, y] = pointerPosition(event, containerRef.current);
      if (drawMode === 'rectangle') {
        event.currentTarget.setPointerCapture(event.pointerId);
        setDraftRect({ x1: x, y1: y, x2: x, y2: y });
        return;
      }
      if (drawMode === 'polygon') {
        const [nx, ny] = displayToNormalized(x, y, layout);
        setDraftPolygon((prev) => [...prev, [nx, ny]]);
      }
    },
    [drawMode, layout, selectedKey]
  );

  const handlePointerMove = useCallback(
    (event: React.PointerEvent<SVGSVGElement>) => {
      if (draggingVertex && containerRef.current) {
        const [x, y] = pointerPosition(event, containerRef.current);
        const [nx, ny] = displayToNormalized(x, y, layout);
        const item = items.find((row) => row.key === draggingVertex.key);
        if (!item?.normalized_polygon) return;
        const next = item.normalized_polygon.map((point, index) =>
          index === draggingVertex.index ? [nx, ny] : point
        );
        onPolygonChange(draggingVertex.key, next);
        return;
      }
      if (draftRect && containerRef.current) {
        const [x, y] = pointerPosition(event, containerRef.current);
        setDraftRect((prev) => (prev ? { ...prev, x2: x, y2: y } : prev));
      }
    },
    [draggingVertex, draftRect, items, layout, onPolygonChange]
  );

  const handlePointerUp = useCallback(
    (event: React.PointerEvent<SVGSVGElement>) => {
      if (draggingVertex) {
        setDraggingVertex(null);
        event.currentTarget.releasePointerCapture(event.pointerId);
        return;
      }
      if (draftRect && selectedKey) {
        const polygon = rectangleToNormalizedPolygon(
          draftRect.x1,
          draftRect.y1,
          draftRect.x2,
          draftRect.y2,
          layout
        );
        commitPolygon(selectedKey, polygon);
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
    },
    [commitPolygon, draftRect, draggingVertex, layout, selectedKey]
  );

  const finishDraftPolygon = useCallback(() => {
    if (!selectedKey || draftPolygon.length < 3) return;
    commitPolygon(selectedKey, draftPolygon);
  }, [commitPolygon, draftPolygon, selectedKey]);

  const deleteSelectedRegion = useCallback(() => {
    if (!selectedKey) return;
    onPolygonChange(selectedKey, null);
    resetDraft();
  }, [onPolygonChange, resetDraft, selectedKey]);

  const zoomIn = () => onZoomChange(Math.min(MAX_ZOOM, zoom + ZOOM_STEP));
  const zoomOut = () => onZoomChange(Math.max(MIN_ZOOM, zoom - ZOOM_STEP));

  const renderPolygon = (
    polygon: number[][],
    color: string,
    itemKey: string,
    selected: boolean,
    item: ReferenceAnnotationCanvasItem,
    index: number
  ) => {
    const points = polygonToSvgPoints(polygon, layout);
    const [labelX, labelY] = normalizedToDisplay(polygon[0][0], polygon[0][1], layout);
    return (
      <g key={`${itemKey}-region`}>
        <polygon
          points={points}
          fill={selected ? `${color}33` : `${color}22`}
          stroke={color}
          strokeWidth={selected ? 2.5 : 1.5}
          style={{ cursor: drawMode === 'select' ? 'pointer' : 'crosshair' }}
          onPointerDown={(event) => {
            event.stopPropagation();
            onSelect(itemKey);
          }}
        />
        {polygon.map(([nx, ny], vertexIndex) => {
          const [cx, cy] = normalizedToDisplay(nx, ny, layout);
          if (!selected || drawMode !== 'select') return null;
          return (
            <circle
              key={`${itemKey}-v-${vertexIndex}`}
              cx={cx}
              cy={cy}
              r={6}
              fill="#fff"
              stroke={color}
              strokeWidth={2}
              style={{ cursor: 'grab', touchAction: 'none' }}
              onPointerDown={(event) => {
                event.stopPropagation();
                onSelect(itemKey);
                setDraggingVertex({ key: itemKey, index: vertexIndex });
                event.currentTarget.setPointerCapture(event.pointerId);
              }}
            />
          );
        })}
        <text
          x={labelX + 4}
          y={labelY + 14}
          fill={color}
          fontSize={12}
          fontWeight={600}
          style={{ pointerEvents: 'none', userSelect: 'none' }}
        >
          {labelForItem(item) || t('clients.extraction_profile.annotations.canvas.unlabeled', { index: index + 1 })}
        </text>
      </g>
    );
  };

  const draftPreview = () => {
    if (draftRect) {
      const minX = Math.min(draftRect.x1, draftRect.x2);
      const maxX = Math.max(draftRect.x1, draftRect.x2);
      const minY = Math.min(draftRect.y1, draftRect.y2);
      const maxY = Math.max(draftRect.y1, draftRect.y2);
      return (
        <rect
          x={minX}
          y={minY}
          width={Math.max(0, maxX - minX)}
          height={Math.max(0, maxY - minY)}
          fill="rgba(25,118,210,0.15)"
          stroke="#1976d2"
          strokeDasharray="4 3"
        />
      );
    }
    if (draftPolygon.length > 0) {
      const displayPoints = draftPolygon
        .map(([nx, ny]) => normalizedToDisplay(nx, ny, layout).join(','))
        .join(' ');
      return (
        <>
          <polyline
            points={displayPoints}
            fill="rgba(25,118,210,0.12)"
            stroke="#1976d2"
            strokeDasharray="4 3"
          />
          {draftPolygon.map(([nx, ny], index) => {
            const [cx, cy] = normalizedToDisplay(nx, ny, layout);
            return <circle key={`draft-${index}`} cx={cx} cy={cy} r={4} fill="#1976d2" />;
          })}
        </>
      );
    }
    return null;
  };

  return (
    <Stack spacing={1}>
      <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap" useFlexGap>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={drawMode}
          onChange={(_, value: AnnotationDrawMode | null) => {
            if (value) onDrawModeChange(value);
          }}
          aria-label={t('clients.extraction_profile.annotations.canvas.tools')}
        >
          <ToggleButton value="select" aria-label={t('clients.extraction_profile.annotations.canvas.select')}>
            <PanToolIcon fontSize="small" />
          </ToggleButton>
          <ToggleButton value="rectangle" aria-label={t('clients.extraction_profile.annotations.canvas.rectangle')}>
            <CropFreeIcon fontSize="small" />
          </ToggleButton>
          <ToggleButton value="polygon" aria-label={t('clients.extraction_profile.annotations.canvas.polygon')}>
            <AddIcon fontSize="small" />
          </ToggleButton>
        </ToggleButtonGroup>
        <Tooltip title={t('clients.extraction_profile.annotations.canvas.delete_region')}>
          <span>
            <IconButton size="small" disabled={!selectedKey} onClick={deleteSelectedRegion}>
              <DeleteOutlineIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
        {drawMode === 'polygon' && draftPolygon.length >= 3 ? (
          <IconButton size="small" color="primary" onClick={finishDraftPolygon}>
            <Typography variant="caption" sx={{ px: 0.5 }}>
              {t('clients.extraction_profile.annotations.canvas.finish_polygon')}
            </Typography>
          </IconButton>
        ) : null}
        <Box sx={{ flex: 1 }} />
        <IconButton size="small" onClick={zoomOut} aria-label={t('clients.extraction_profile.annotations.canvas.zoom_out')}>
          <ZoomOutIcon fontSize="small" />
        </IconButton>
        <Typography variant="caption" color="text.secondary" sx={{ minWidth: 40, textAlign: 'center' }}>
          {Math.round(zoom * 100)}%
        </Typography>
        <IconButton size="small" onClick={zoomIn} aria-label={t('clients.extraction_profile.annotations.canvas.zoom_in')}>
          <ZoomInIcon fontSize="small" />
        </IconButton>
        <IconButton
          size="small"
          onClick={() => onZoomChange(1)}
          aria-label={t('clients.extraction_profile.annotations.canvas.reset_zoom')}
        >
          <RemoveIcon fontSize="small" />
        </IconButton>
      </Stack>

      <Typography variant="caption" color="text.secondary">
        {drawMode === 'rectangle'
          ? t('clients.extraction_profile.annotations.canvas.rectangle_hint')
          : drawMode === 'polygon'
            ? t('clients.extraction_profile.annotations.canvas.polygon_hint')
            : t('clients.extraction_profile.annotations.canvas.select_hint')}
      </Typography>

      <Box
        ref={containerRef}
        sx={{
          position: 'relative',
          width: '100%',
          minHeight: { xs: 220, sm: 320 },
          maxHeight: { xs: 360, md: 480 },
          border: 1,
          borderColor: 'divider',
          borderRadius: 1,
          overflow: 'auto',
          bgcolor: 'grey.100',
          touchAction: drawMode === 'select' ? 'auto' : 'none',
        }}
      >
        <Box
          sx={{
            position: 'relative',
            width: `${zoom * 100}%`,
            height: containerSize.height * zoom,
            minHeight: { xs: 220, sm: 320 },
            mx: 'auto',
          }}
        >
          {imageSrc ? (
            <Box
              component="img"
              ref={imageRef}
              src={imageSrc}
              alt={imageAlt}
              onLoad={handleImageLoad}
              sx={{
                position: 'absolute',
                inset: 0,
                width: '100%',
                height: '100%',
                objectFit: 'contain',
                userSelect: 'none',
                pointerEvents: 'none',
              }}
            />
          ) : (
            <Box
              sx={{
                position: 'absolute',
                inset: 0,
                display: 'grid',
                placeItems: 'center',
                color: 'text.secondary',
                px: 2,
                textAlign: 'center',
              }}
            >
              <Typography variant="body2">{t('clients.extraction_profile.annotations.canvas.no_image')}</Typography>
            </Box>
          )}

          <svg
            width="100%"
            height="100%"
            style={{ position: 'absolute', inset: 0 }}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
          >
            {items.map((item, index) => {
              if (!item.normalized_polygon || item.normalized_polygon.length === 0) return null;
              const color = regionColor(index);
              return renderPolygon(
                item.normalized_polygon,
                color,
                item.key,
                item.key === selectedKey,
                item,
                index
              );
            })}
            {draftPreview()}
          </svg>
        </Box>
      </Box>
    </Stack>
  );
}

export function isPointInLayout(x: number, y: number, layout: ImageLayout): boolean {
  return (
    x >= layout.offsetX &&
    x <= layout.offsetX + layout.displayW &&
    y >= layout.offsetY &&
    y <= layout.offsetY + layout.displayH
  );
}
