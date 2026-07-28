import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, FlatList, Image, Text, View } from 'react-native';

import type { CapturePhotoRow } from '../database/schema/captureSchema';
import type { ConfirmedLocalResultRow } from '../database/repositories/confirmedLocalResultRepository';
import type { LocalDetectionDraftRow } from '../database/repositories/localDetectionDraftRepository';
import type { ConfirmLocalResultEdits } from '../features/authoritativeLocalResult/confirmLocalResultService';
import type { AppServices } from '../runtime/bootstrap/createAppServices';
import { Button, ErrorText, Input, SmallButton, messageOf, styles } from '../ui';

export interface LocalResultReviewScreenProps {
  services: AppServices;
  sessionId: string;
  userId: string;
  onBack: () => void;
  onDone: (sessionId: string) => void;
  onError: (message: string | null) => void;
}

interface ReviewItem {
  readonly photo: CapturePhotoRow;
  readonly draft: LocalDetectionDraftRow | null;
  readonly confirmed: ConfirmedLocalResultRow | null;
}

const REVIEWABLE_DRAFT_STATUSES = new Set([
  'RESOLVED',
  'UNRESOLVED',
  'INVALID',
  'AMBIGUOUS',
  'FAILED',
  'FAILED_RETRYABLE',
  'DETECTED_UNVERIFIED',
  'PENDING',
  'SCANNING',
]);

function initialEdits(
  draft: LocalDetectionDraftRow | null,
  confirmed: ConfirmedLocalResultRow | null,
): ConfirmLocalResultEdits {
  if (confirmed) {
    return {
      internalCode: confirmed.confirmed_internal_code,
      quantity: confirmed.confirmed_quantity,
      quantityStatus: confirmed.quantity_status,
    };
  }
  const qtyStatus =
    draft?.quantity_status === 'PRESENT' || draft?.quantity != null ? 'PRESENT' : 'MISSING';
  return {
    internalCode: draft?.internal_code ?? '',
    quantity: draft?.quantity ?? null,
    quantityStatus: qtyStatus as ConfirmLocalResultEdits['quantityStatus'],
  };
}

function draftNeedsRescan(draft: LocalDetectionDraftRow | null): boolean {
  if (!draft) {
    return true;
  }
  return draft.status === 'NOT_APPLICABLE';
}

function labelForDraftStatus(draft: LocalDetectionDraftRow | null, scanning: boolean): string {
  if (scanning) {
    return 'Escaneando…';
  }
  if (!draft) {
    return 'Sin escaneo local';
  }
  switch (draft.status) {
    case 'RESOLVED':
      return 'Detectado';
    case 'UNRESOLVED':
      return 'Sin códigos detectados';
    case 'AMBIGUOUS':
      return 'Ambiguo — revisá / corregí';
    case 'INVALID':
    case 'DETECTED_UNVERIFIED':
      return 'Código no verificado — corregí si hace falta';
    case 'FAILED':
    case 'FAILED_RETRYABLE':
      return `Escaneo falló${draft.error_code ? ` (${draft.error_code})` : ''}`;
    case 'PENDING':
    case 'SCANNING':
      return 'Escaneando…';
    default:
      return draft.status;
  }
}

export function LocalResultReviewScreen({
  services,
  sessionId,
  userId,
  onBack,
  onDone,
  onError,
}: LocalResultReviewScreenProps): JSX.Element {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [editsByPhotoId, setEditsByPhotoId] = useState<Record<string, ConfirmLocalResultEdits>>({});
  const [loading, setLoading] = useState(true);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [rescanning, setRescanning] = useState(false);
  const rescanAttemptedRef = useRef(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const photos = (await services.capture.getSessionSnapshot(sessionId)).photos.filter(
        (p) => p.status === 'stable',
      );
      const drafts = await services.localDetectionDrafts.listForSession(sessionId);
      const confirmed = await services.confirmedLocalResults.listForSession(sessionId);
      const draftByPhoto = new Map<string, LocalDetectionDraftRow>();
      for (const d of drafts) {
        const prev = draftByPhoto.get(d.capture_photo_id);
        if (!prev) {
          draftByPhoto.set(d.capture_photo_id, d);
          continue;
        }
        // Prefer a real scan outcome over a capture-time NOT_APPLICABLE placeholder.
        if (prev.status === 'NOT_APPLICABLE' && d.status !== 'NOT_APPLICABLE') {
          draftByPhoto.set(d.capture_photo_id, d);
        }
      }
      const confirmedByPhoto = new Map(confirmed.map((c) => [c.capture_photo_id, c]));
      const nextItems = photos.map((photo) => {
        const draft = draftByPhoto.get(photo.id) ?? null;
        return {
          photo,
          draft: draft?.status === 'NOT_APPLICABLE' ? null : draft,
          confirmed: confirmedByPhoto.get(photo.id) ?? null,
        };
      });
      setItems(nextItems);
      setEditsByPhotoId((prev) => {
        const merged = { ...prev };
        for (const item of nextItems) {
          const existing = merged[item.photo.id];
          if (!existing) {
            merged[item.photo.id] = initialEdits(item.draft, item.confirmed);
            continue;
          }
          // After a late rescan, hydrate empty manual fields from the new draft.
          if (
            !item.confirmed &&
            !existing.internalCode.trim() &&
            (item.draft?.internal_code || item.draft?.quantity != null)
          ) {
            merged[item.photo.id] = initialEdits(item.draft, item.confirmed);
          }
        }
        return merged;
      });
      return nextItems;
    } catch (e) {
      onError(messageOf(e));
      return [];
    } finally {
      setLoading(false);
    }
  }, [onError, services, sessionId]);

  const ensureLocalScans = useCallback(async () => {
    if (!services.config.flags.mobileLocalCodeScan) {
      return;
    }
    setRescanning(true);
    try {
      const snapshot = await services.capture.getSessionSnapshot(sessionId);
      const drafts = await services.localDetectionDrafts.listForSession(sessionId);
      const byPhoto = new Map<string, LocalDetectionDraftRow[]>();
      for (const d of drafts) {
        const list = byPhoto.get(d.capture_photo_id) ?? [];
        list.push(d);
        byPhoto.set(d.capture_photo_id, list);
      }
      const targets = snapshot.photos.filter((p) => {
        if (p.status !== 'stable') {
          return false;
        }
        const rows = byPhoto.get(p.id) ?? [];
        const best =
          rows.find((r) => REVIEWABLE_DRAFT_STATUSES.has(r.status)) ?? rows[0] ?? null;
        return draftNeedsRescan(best);
      });
      for (const photo of targets) {
        try {
          await services.uploadQueue.rescanPhotoForLocalReview(photo.id);
        } catch (e) {
          onError(messageOf(e));
        }
      }
    } finally {
      setRescanning(false);
      await reload();
    }
  }, [onError, reload, services, sessionId]);

  useEffect(() => {
    void (async () => {
      await reload();
      if (!rescanAttemptedRef.current) {
        rescanAttemptedRef.current = true;
        await ensureLocalScans();
      }
    })();
    const t = setInterval(() => void reload(), 4000);
    return () => clearInterval(t);
  }, [ensureLocalScans, reload]);

  const summary = useMemo(() => {
    const total = items.length;
    const confirmed = items.filter((i) => i.confirmed != null).length;
    const pendingReview = items.filter((i) => i.confirmed == null).length;
    const synced = items.filter(
      (i) => i.confirmed?.sync_status === 'SYNCED' && !i.confirmed.applied_at,
    ).length;
    const applied = items.filter((i) => i.confirmed?.applied_at != null).length;
    const errors = items.filter((i) =>
      ['CONFLICT', 'REJECTED', 'FAILED_TERMINAL'].includes(i.confirmed?.sync_status ?? ''),
    ).length;
    return { total, confirmed, pendingReview, excluded: 0, synced, applied, errors };
  }, [items]);

  const allConfirmed = items.length > 0 && summary.pendingReview === 0;

  const updateEdit = (photoId: string, patch: Partial<ConfirmLocalResultEdits>) => {
    setEditsByPhotoId((prev) => ({
      ...prev,
      [photoId]: { ...prev[photoId]!, ...patch },
    }));
  };

  const confirmPhoto = async (item: ReviewItem) => {
    const edits = editsByPhotoId[item.photo.id];
    if (!edits) return;
    if (!edits.internalCode.trim()) {
      onError('Ingresá el código interno antes de confirmar.');
      return;
    }
    Alert.alert(
      'Confirmar resultado',
      'Este resultado se enviará como resultado final.',
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Confirmar',
          onPress: () => {
            setConfirmingId(item.photo.id);
            void services.confirmLocalResult
              .confirm({
                capturePhotoId: item.photo.id,
                captureSessionId: sessionId,
                clientFileId: item.photo.client_file_id,
                confirmedByUserId: userId,
                edits,
                draft: item.draft,
              })
              .then(() => reload())
              .catch((e) => onError(messageOf(e)))
              .finally(() => setConfirmingId(null));
          },
        },
      ],
    );
  };

  const excludePhoto = async (assetId: string) => {
    await services.capture.loadSession(sessionId, false);
    await services.capture.exclude(assetId);
    await reload();
  };

  if (loading && items.length === 0) {
    return <Text style={styles.muted}>Cargando revisión local…</Text>;
  }

  return (
    <FlatList
      data={items}
      keyExtractor={(item) => item.photo.id}
      ListHeaderComponent={
        <View>
          <SmallButton label="← Revisión de captura" onPress={onBack} />
          <Text style={styles.h2}>Confirmación local de códigos</Text>
          <Text style={styles.row}>
            Total: {summary.total} · Confirmadas: {summary.confirmed} · Pendientes:{' '}
            {summary.pendingReview} · Sincronizadas: {summary.synced} · Aplicadas (final):{' '}
            {summary.applied} · Errores: {summary.errors}
          </Text>
          {rescanning ? <Text style={styles.muted}>Reejecutando escaneo local…</Text> : null}
          {!allConfirmed ? (
            <ErrorText text="Confirmá el código de cada fotografía antes de continuar." />
          ) : null}
          <SmallButton
            label="Reescanear pendientes"
            disabled={rescanning}
            onPress={() => {
              rescanAttemptedRef.current = true;
              void ensureLocalScans();
            }}
          />
          <Button
            label="Continuar a cargas"
            disabled={!allConfirmed}
            onPress={() => onDone(sessionId)}
          />
        </View>
      }
      ListEmptyComponent={<Text style={styles.muted}>No hay fotografías estables para revisar.</Text>}
      renderItem={({ item }) => {
        const edits = editsByPhotoId[item.photo.id] ?? initialEdits(item.draft, item.confirmed);
        const isConfirmed = item.confirmed != null;
        const scanning =
          rescanning ||
          item.draft?.status === 'PENDING' ||
          item.draft?.status === 'SCANNING';
        return (
          <View style={styles.card}>
            <Image source={{ uri: item.photo.uri }} style={styles.thumb} />
            <Text style={styles.photoText} numberOfLines={1}>
              {item.photo.display_name}
            </Text>
            <Text style={styles.muted}>{labelForDraftStatus(item.draft, scanning)}</Text>
            <Text style={styles.muted}>
              Detectado: {item.draft?.internal_code ?? '—'} · Cant:{' '}
              {item.draft?.quantity ?? '—'}
            </Text>
            {!isConfirmed && !item.draft?.internal_code ? (
              <Text style={styles.muted}>
                Ingresá el código manualmente si el escaneo no lo detectó.
              </Text>
            ) : null}
            <Input
              value={edits.internalCode}
              editable={!isConfirmed}
              placeholder="Código interno"
              onChangeText={(v) => updateEdit(item.photo.id, { internalCode: v })}
            />
            <Input
              value={edits.quantity != null ? String(edits.quantity) : ''}
              editable={!isConfirmed && edits.quantityStatus === 'PRESENT'}
              placeholder="Cantidad"
              keyboardType="number-pad"
              onChangeText={(v) => {
                const trimmed = v.trim();
                updateEdit(item.photo.id, {
                  quantity: trimmed ? Number.parseInt(trimmed, 10) : null,
                  quantityStatus: trimmed ? 'PRESENT' : 'MISSING',
                });
              }}
            />
            <SmallButton
              label={edits.quantityStatus === 'PRESENT' ? 'Sin cantidad' : 'Con cantidad'}
              disabled={isConfirmed}
              onPress={() =>
                updateEdit(item.photo.id, {
                  quantityStatus: edits.quantityStatus === 'PRESENT' ? 'MISSING' : 'PRESENT',
                  quantity: edits.quantityStatus === 'PRESENT' ? null : edits.quantity ?? 1,
                })
              }
            />
            {isConfirmed ? (
              <Text style={styles.muted}>
                Confirmado · sync: {item.confirmed?.sync_status ?? '—'}
              </Text>
            ) : (
              <Button
                label={confirmingId === item.photo.id ? 'Confirmando…' : 'Confirmar resultado'}
                disabled={confirmingId === item.photo.id || scanning}
                onPress={() => void confirmPhoto(item)}
              />
            )}
            <SmallButton
              label="Excluir foto"
              onPress={() => void excludePhoto(item.photo.asset_id)}
            />
          </View>
        );
      }}
    />
  );
}
