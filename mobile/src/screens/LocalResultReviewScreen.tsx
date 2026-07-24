import { useCallback, useEffect, useMemo, useState } from 'react';
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
        if (!draftByPhoto.has(d.capture_photo_id) && REVIEWABLE_DRAFT_STATUSES.has(d.status)) {
          draftByPhoto.set(d.capture_photo_id, d);
        }
      }
      const confirmedByPhoto = new Map(confirmed.map((c) => [c.capture_photo_id, c]));
      const nextItems = photos.map((photo) => ({
        photo,
        draft: draftByPhoto.get(photo.id) ?? null,
        confirmed: confirmedByPhoto.get(photo.id) ?? null,
      }));
      setItems(nextItems);
      setEditsByPhotoId((prev) => {
        const merged = { ...prev };
        for (const item of nextItems) {
          if (!merged[item.photo.id]) {
            merged[item.photo.id] = initialEdits(item.draft, item.confirmed);
          }
        }
        return merged;
      });
    } catch (e) {
      onError(messageOf(e));
    } finally {
      setLoading(false);
    }
  }, [onError, services, sessionId]);

  useEffect(() => {
    void reload();
    const t = setInterval(() => void reload(), 4000);
    return () => clearInterval(t);
  }, [reload]);

  const summary = useMemo(() => {
    const total = items.length;
    const confirmed = items.filter((i) => i.confirmed != null).length;
    const pendingReview = items.filter((i) => i.confirmed == null).length;
    const synced = items.filter((i) => i.confirmed?.sync_status === 'SYNCED').length;
    const errors = items.filter((i) =>
      ['CONFLICT', 'REJECTED', 'FAILED_TERMINAL'].includes(i.confirmed?.sync_status ?? ''),
    ).length;
    return { total, confirmed, pendingReview, excluded: 0, synced, errors };
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
            {summary.pendingReview} · Sincronizadas: {summary.synced} · Errores: {summary.errors}
          </Text>
          {!allConfirmed ? (
            <ErrorText text="Confirmá el código de cada fotografía antes de continuar." />
          ) : null}
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
        return (
          <View style={styles.card}>
            <Image source={{ uri: item.photo.uri }} style={styles.thumb} />
            <Text style={styles.photoText} numberOfLines={1}>
              {item.photo.display_name}
            </Text>
            <Text style={styles.muted}>
              Detectado: {item.draft?.internal_code ?? '—'} · Cant:{' '}
              {item.draft?.quantity ?? '—'}
            </Text>
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
                disabled={confirmingId === item.photo.id}
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
