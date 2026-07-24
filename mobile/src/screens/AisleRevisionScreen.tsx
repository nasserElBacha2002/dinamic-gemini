import { useMemo, useState } from 'react';
import { Text, TextInput, View } from 'react-native';

import type { AppServices } from '../runtime/bootstrap/createAppServices';
import type { AisleDto, InventoryListItemDto } from '../services/api/types';
import type {
  AisleRevisionDiffDto,
  AisleRevisionType,
} from '../features/aisleRevision/aisleRevisionApi';
import { Button, ErrorText, styles } from '../ui';

export interface AisleRevisionScreenProps {
  services: AppServices;
  inventory: InventoryListItemDto;
  aisle: AisleDto;
  userId: string;
  onBack: () => void;
  onOpenHistory?: () => void;
  onError: (message: string | null) => void;
}

const REVISION_TYPES: { value: AisleRevisionType; label: string }[] = [
  { value: 'MANUAL_CORRECTION', label: 'Corrección manual' },
  { value: 'EXCLUSION_CHANGE', label: 'Cambio de exclusión' },
  { value: 'REOPEN_AND_EDIT', label: 'Reabrir y editar' },
];

export function AisleRevisionScreen({
  services,
  inventory,
  aisle,
  userId,
  onBack,
  onOpenHistory,
  onError,
}: AisleRevisionScreenProps) {
  const service = services.aisleRevision;
  const [revisionType, setRevisionType] = useState<AisleRevisionType>('MANUAL_CORRECTION');
  const [reason, setReason] = useState('Corrección operador');
  const [revisionId, setRevisionId] = useState<string | null>(null);
  const [baseFinalizationId, setBaseFinalizationId] = useState<string | null>(null);
  const [assetId, setAssetId] = useState('');
  const [internalCode, setInternalCode] = useState('');
  const [quantity, setQuantity] = useState('');
  const [diff, setDiff] = useState<AisleRevisionDiffDto | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const warning = useMemo(
    () => 'Los cambios se aplican como una nueva versión del pasillo. No se borra el historial.',
    [],
  );

  if (!service?.isActionVisible()) {
    return (
      <View>
        <ErrorText text="Corrección de pasillo deshabilitada." />
        <Button label="Volver" onPress={onBack} />
      </View>
    );
  }

  const startRevision = () => {
    setBusy(true);
    setMessage(null);
    onError(null);
    void service
      .createRevision({
        inventoryId: inventory.id,
        aisleId: aisle.id,
        revisionType,
        reason: reason.trim() || 'Corrección operador',
        requestedBy: userId,
      })
      .then((result) => {
        if ('local' in result && result.local) {
          setRevisionId(result.revision_id);
          setMessage('Borrador guardado localmente. Sincronizá cuando haya conexión.');
          return;
        }
        setRevisionId(result.revision.id);
        setBaseFinalizationId(result.revision.base_finalization_id);
        setMessage('Corrección iniciada.');
      })
      .catch((e) => {
        const text = e instanceof Error ? e.message : String(e);
        setMessage(text);
        onError(text);
      })
      .finally(() => setBusy(false));
  };

  const saveItemChange = () => {
    if (!revisionId || !assetId.trim()) {
      setMessage('Ingresá el identificador de la imagen.');
      return;
    }
    setBusy(true);
    onError(null);
    void service
      .updateItem({
        inventoryId: inventory.id,
        aisleId: aisle.id,
        revisionId,
        assetId: assetId.trim(),
        internalCode: internalCode.trim() || null,
        quantity: quantity.trim() ? Number(quantity) : null,
      })
      .then(() => {
        setMessage('Cambio registrado.');
      })
      .catch((e) => onError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false));
  };

  const loadDiff = () => {
    if (!revisionId) return;
    setBusy(true);
    void service
      .getDiff(inventory.id, aisle.id, revisionId)
      .then((d) => {
        setDiff(d);
        setBaseFinalizationId(d.revision.base_finalization_id);
      })
      .catch((e) => onError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false));
  };

  const apply = () => {
    if (!revisionId || !baseFinalizationId) {
      setMessage('Consultá las diferencias antes de aplicar.');
      return;
    }
    setBusy(true);
    onError(null);
    void service
      .applyRevision({
        inventoryId: inventory.id,
        aisleId: aisle.id,
        revisionId,
        expectedBaseFinalizationId: baseFinalizationId,
        appliedBy: userId,
      })
      .then((rev) => {
        setMessage(`Corrección aplicada. Estado: ${rev.status}`);
      })
      .catch((e) => onError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false));
  };

  return (
    <View>
      <Text style={styles.h2}>Corregir pasillo</Text>
      <Text style={styles.muted}>{warning}</Text>
      <Text style={styles.row}>Pasillo: {aisle.code ?? aisle.id}</Text>

      {!revisionId ? (
        <>
          <Text style={styles.row}>Tipo de corrección</Text>
          {REVISION_TYPES.map((t) => (
            <Button
              key={t.value}
              label={`${revisionType === t.value ? '●' : '○'} ${t.label}`}
              onPress={() => setRevisionType(t.value)}
            />
          ))}
          <Text style={styles.row}>Motivo</Text>
          <TextInput
            value={reason}
            onChangeText={setReason}
            style={styles.input}
            placeholder="Motivo de la corrección"
          />
          <Button label={busy ? 'Iniciando…' : 'Iniciar corrección'} onPress={startRevision} />
        </>
      ) : (
        <>
          <Text style={styles.row}>Corrección: {revisionId}</Text>
          <Text style={styles.row}>Imagen (asset id)</Text>
          <TextInput
            value={assetId}
            onChangeText={setAssetId}
            style={styles.input}
            placeholder="Identificador de imagen"
            autoCapitalize="none"
          />
          <Text style={styles.row}>Código interno</Text>
          <TextInput
            value={internalCode}
            onChangeText={setInternalCode}
            style={styles.input}
            placeholder="Código corregido"
            autoCapitalize="characters"
          />
          <Text style={styles.row}>Cantidad (opcional)</Text>
          <TextInput
            value={quantity}
            onChangeText={setQuantity}
            style={styles.input}
            placeholder="Cantidad"
            keyboardType="numeric"
          />
          <Button label={busy ? 'Guardando…' : 'Registrar cambio'} onPress={saveItemChange} />
          <Button label="Ver diferencias" onPress={loadDiff} />
          {diff ? (
            <>
              <Text style={styles.row}>
                Cambios: {diff.entries.filter((e) => e.kind !== 'UNCHANGED').length} de{' '}
                {diff.entries.length}
              </Text>
              {diff.entries.slice(0, 30).map((entry) => (
                <Text key={entry.asset_id} style={styles.muted}>
                  {entry.asset_id}: {entry.kind} · {entry.base_internal_code ?? '—'} →{' '}
                  {entry.proposed_internal_code ?? '—'}
                </Text>
              ))}
            </>
          ) : null}
          <Button label={busy ? 'Aplicando…' : 'Aplicar corrección'} onPress={apply} />
        </>
      )}

      {service.isHistoryVisible() && onOpenHistory ? (
        <Button label="Ver historial del pasillo" onPress={onOpenHistory} />
      ) : null}
      {message ? <Text style={styles.muted}>{message}</Text> : null}
      <Button label="Volver" onPress={onBack} />
    </View>
  );
}
