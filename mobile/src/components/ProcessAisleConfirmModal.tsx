/**
 * Procesar pasillo hub: process photos, upload local results, view results, excluded photos.
 */

import { useEffect, useState } from 'react';
import { Modal, ScrollView, Text, TouchableOpacity, View } from 'react-native';

import type { ConfirmedLocalResultRow } from '../database/repositories/confirmedLocalResultRepository';
import {
  formatShortDate,
  labelForLocalSyncStatus,
} from '../features/processing/aisleProcessDialogHelpers';
import {
  INHERITED_IDENTIFICATION_MODE,
  PROCESS_AISLE_IDENTIFICATION_OPTIONS,
  labelForIdentificationMode,
  preferenceFromSelection,
  selectionFromPreference,
  type AisleIdentificationMode,
  type IdentificationModeSelection,
} from '../features/processing/processingMode';
import { Button, ErrorText, SmallButton, styles } from '../ui';

type DialogStep = 'menu' | 'process' | 'upload_local';

export interface ProcessAisleConfirmModalProps {
  visible: boolean;
  inventoryName: string;
  aisleName: string;
  uploadedCount: number;
  pendingCount: number;
  /** Pending / failed local confirmed results for this aisle session. */
  pendingLocalResultCount: number;
  excludedPhotoCount: number;
  /** Rows shown when choosing "Subir resultado local". */
  localResults: readonly ConfirmedLocalResultRow[];
  preference: AisleIdentificationMode | null;
  busy: boolean;
  error: string | null;
  uploadLocalBusy?: boolean;
  uploadLocalMessage?: string | null;
  onClose: () => void;
  onConfirm: (selection: IdentificationModeSelection) => void;
  /** Sync one result (preferred) or all pending for this aisle session. */
  onUploadLocalResults: (resultId?: string | null) => void;
  onViewResults: () => void;
  onExcludedPhotos: () => void;
}

export function ProcessAisleConfirmModal({
  visible,
  inventoryName,
  aisleName,
  uploadedCount,
  pendingCount,
  pendingLocalResultCount,
  excludedPhotoCount,
  localResults,
  preference,
  busy,
  error,
  uploadLocalBusy = false,
  uploadLocalMessage = null,
  onClose,
  onConfirm,
  onUploadLocalResults,
  onViewResults,
  onExcludedPhotos,
}: ProcessAisleConfirmModalProps) {
  const [step, setStep] = useState<DialogStep>('menu');
  const [draft, setDraft] = useState<IdentificationModeSelection>(
    selectionFromPreference(preference),
  );
  const [selectedResultId, setSelectedResultId] = useState<string | null>(null);

  useEffect(() => {
    if (!visible) return;
    setStep('menu');
    setDraft(selectionFromPreference(preference));
    setSelectedResultId(null);
  }, [visible, preference]);

  const selectedLabel = labelForIdentificationMode(preferenceFromSelection(draft));
  const anyBusy = busy || uploadLocalBusy;

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={styles.modalBackdrop}>
        <View style={styles.modalCard}>
          <ScrollView>
            {step === 'menu' ? (
              <>
                <Text style={styles.h2}>Procesar pasillo</Text>
                <Text style={styles.row}>
                  Inventario: {inventoryName || '—'}
                </Text>
                <Text style={styles.row}>Pasillo: {aisleName || '—'}</Text>
                <Text style={styles.row}>
                  Fotos cargadas: {uploadedCount} · Pendientes: {pendingCount}
                </Text>
                {pendingLocalResultCount > 0 || excludedPhotoCount > 0 ? (
                  <Text style={[styles.muted, { marginTop: 6 }]} accessibilityLiveRegion="polite">
                    {pendingLocalResultCount > 0
                      ? `${pendingLocalResultCount} resultado(s) local(es) pendiente(s)`
                      : null}
                    {pendingLocalResultCount > 0 && excludedPhotoCount > 0 ? ' · ' : null}
                    {excludedPhotoCount > 0
                      ? `${excludedPhotoCount} foto(s) excluida(s)`
                      : null}
                  </Text>
                ) : null}
                <Text style={[styles.row, { marginTop: 12 }]}>¿Qué querés hacer?</Text>

                <ActionRow
                  title="Procesar fotos"
                  description="Procesar las fotos del pasillo y enviar el trabajo al servidor."
                  disabled={anyBusy}
                  testID="process-aisle-action-process"
                  onPress={() => setStep('process')}
                />
                <ActionRow
                  title="Subir resultado local"
                  description="Enviar resultados confirmados en este dispositivo (sin reprocesar)."
                  {...(pendingLocalResultCount > 0
                    ? { badge: String(pendingLocalResultCount) }
                    : {})}
                  disabled={anyBusy}
                  testID="process-aisle-action-upload-local"
                  onPress={() => setStep('upload_local')}
                />
                <ActionRow
                  title="Ver resultados"
                  description="Consultar procesamientos locales y del servidor de este pasillo."
                  disabled={anyBusy}
                  testID="process-aisle-action-results"
                  onPress={() => {
                    onClose();
                    onViewResults();
                  }}
                />
                <ActionRow
                  title="Fotos excluidas"
                  description="Revisar y volver a incluir fotos excluidas del pasillo."
                  {...(excludedPhotoCount > 0 ? { badge: String(excludedPhotoCount) } : {})}
                  disabled={anyBusy}
                  testID="process-aisle-action-excluded"
                  onPress={() => {
                    onClose();
                    onExcludedPhotos();
                  }}
                />

                {error ? <ErrorText text={error} /> : null}
                <View style={styles.nav}>
                  <SmallButton label="Cancelar" disabled={anyBusy} onPress={onClose} />
                </View>
              </>
            ) : null}

            {step === 'process' ? (
              <>
                <Text style={styles.h2}>Procesar fotos</Text>
                <Text style={styles.muted}>Tipo de procesamiento</Text>
                <Text style={styles.muted} accessibilityLiveRegion="polite">
                  Seleccionado: {selectedLabel}
                </Text>
                {PROCESS_AISLE_IDENTIFICATION_OPTIONS.map((option) => {
                  const active = draft === option.value;
                  return (
                    <TouchableOpacity
                      key={option.value}
                      accessibilityRole="radio"
                      accessibilityState={{ selected: active, disabled: anyBusy }}
                      accessibilityLabel={`${option.label}. ${option.description}`}
                      disabled={anyBusy}
                      style={[styles.pickerItem, active ? styles.pickerItemActive : null]}
                      onPress={() => setDraft(option.value)}
                    >
                      <Text style={styles.row}>{option.label}</Text>
                      <Text style={styles.muted}>{option.description}</Text>
                    </TouchableOpacity>
                  );
                })}
                {error ? <ErrorText text={error} /> : null}
                <View style={styles.nav}>
                  <SmallButton
                    label="Volver"
                    disabled={anyBusy}
                    onPress={() => setStep('menu')}
                  />
                  <Button
                    label={busy ? 'Iniciando…' : 'Confirmar e iniciar'}
                    disabled={anyBusy}
                    onPress={() => onConfirm(draft)}
                  />
                </View>
                <Text style={styles.muted}>
                  {draft === INHERITED_IDENTIFICATION_MODE
                    ? 'Se usará la configuración heredada del pasillo, inventario o cliente.'
                    : `Se enviará el modo ${draft} al iniciar el trabajo.`}
                </Text>
              </>
            ) : null}

            {step === 'upload_local' ? (
              <>
                <Text style={styles.h2}>Subir resultado local</Text>
                <Text style={styles.muted}>
                  Elegí un resultado de este pasillo. Solo se sincroniza la selección (no otros
                  pasillos). La operación es idempotente.
                </Text>
                {localResults.length === 0 ? (
                  <Text style={[styles.row, { marginTop: 8 }]}>
                    No hay resultados locales confirmados para este pasillo. Confirmalos en la
                    revisión local antes de subir.
                  </Text>
                ) : (
                  localResults.map((row) => {
                    const active = selectedResultId === row.id;
                    return (
                      <TouchableOpacity
                        key={row.id}
                        accessibilityRole="radio"
                        accessibilityState={{ selected: active, disabled: anyBusy }}
                        testID={`upload-local-result-${row.id}`}
                        disabled={anyBusy}
                        style={[styles.pickerItem, { marginTop: 6 }, active ? styles.pickerItemActive : null]}
                        onPress={() => setSelectedResultId(row.id)}
                      >
                        <Text style={styles.row}>
                          {row.confirmed_internal_code} · {formatShortDate(row.confirmed_at)}
                        </Text>
                        <Text style={styles.muted}>
                          Estado: {labelForLocalSyncStatus(row.sync_status)}
                          {row.sync_last_error_code ? ` · ${row.sync_last_error_code}` : ''}
                        </Text>
                      </TouchableOpacity>
                    );
                  })
                )}
                {uploadLocalMessage ? (
                  <Text style={[styles.muted, { marginTop: 8 }]}>{uploadLocalMessage}</Text>
                ) : null}
                {error ? <ErrorText text={error} /> : null}
                <View style={styles.nav}>
                  <SmallButton
                    label="Volver"
                    disabled={anyBusy}
                    onPress={() => setStep('menu')}
                  />
                  <Button
                    label={
                      uploadLocalBusy
                        ? 'Subiendo…'
                        : selectedResultId
                          ? 'Subir seleccionado'
                          : 'Subir pendientes del pasillo'
                    }
                    disabled={anyBusy || localResults.length === 0}
                    onPress={() => onUploadLocalResults(selectedResultId)}
                  />
                </View>
              </>
            ) : null}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

function ActionRow({
  title,
  description,
  badge,
  disabled,
  onPress,
  testID,
}: {
  title: string;
  description: string;
  badge?: string;
  disabled: boolean;
  onPress: () => void;
  testID: string;
}): JSX.Element {
  return (
    <TouchableOpacity
      testID={testID}
      accessibilityRole="button"
      disabled={disabled}
      style={[styles.pickerItem, { marginTop: 8 }]}
      onPress={onPress}
    >
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text style={styles.row}>{title}</Text>
        {badge ? <Text style={styles.muted}>({badge})</Text> : null}
      </View>
      <Text style={styles.muted}>{description}</Text>
    </TouchableOpacity>
  );
}
