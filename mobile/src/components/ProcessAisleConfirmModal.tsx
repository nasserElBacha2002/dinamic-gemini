import { useEffect, useState } from 'react';
import { Modal, Text, TouchableOpacity, View } from 'react-native';

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

export interface ProcessAisleConfirmModalProps {
  visible: boolean;
  inventoryName: string;
  aisleName: string;
  uploadedCount: number;
  pendingCount: number;
  /** Session preference: null = inherit. Used only to seed draft when opening. */
  preference: AisleIdentificationMode | null;
  busy: boolean;
  error: string | null;
  onClose: () => void;
  /** Confirm commits the draft selection (does not mutate preference while picking). */
  onConfirm: (selection: IdentificationModeSelection) => void;
}

export function ProcessAisleConfirmModal({
  visible,
  inventoryName,
  aisleName,
  uploadedCount,
  pendingCount,
  preference,
  busy,
  error,
  onClose,
  onConfirm,
}: ProcessAisleConfirmModalProps) {
  const [draft, setDraft] = useState<IdentificationModeSelection>(
    selectionFromPreference(preference),
  );

  useEffect(() => {
    if (!visible) return;
    setDraft(selectionFromPreference(preference));
  }, [visible, preference]);

  const selectedLabel = labelForIdentificationMode(preferenceFromSelection(draft));

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={styles.modalBackdrop}>
        <View style={styles.modalCard}>
          <Text style={styles.h2}>Confirmar procesamiento</Text>
          <Text style={styles.row}>
            Inventario: {inventoryName || '—'}
          </Text>
          <Text style={styles.row}>Pasillo: {aisleName || '—'}</Text>
          <Text style={styles.row}>
            Fotos cargadas: {uploadedCount} · Pendientes: {pendingCount}
          </Text>
          <Text style={[styles.row, { marginTop: 8 }]}>Tipo de procesamiento</Text>
          <Text style={styles.muted} accessibilityLiveRegion="polite">
            Seleccionado: {selectedLabel}
          </Text>
          {PROCESS_AISLE_IDENTIFICATION_OPTIONS.map((option) => {
            const active = draft === option.value;
            return (
              <TouchableOpacity
                key={option.value}
                accessibilityRole="radio"
                accessibilityState={{ selected: active, disabled: busy }}
                accessibilityLabel={`${option.label}. ${option.description}`}
                disabled={busy}
                style={[styles.pickerItem, active ? styles.pickerItemActive : null]}
                onPress={() => {
                  setDraft(option.value);
                }}
              >
                <Text style={styles.row}>{option.label}</Text>
                <Text style={styles.muted}>{option.description}</Text>
              </TouchableOpacity>
            );
          })}
          {error ? <ErrorText text={error} /> : null}
          <View style={styles.nav}>
            <SmallButton label="Cancelar" disabled={busy} onPress={onClose} />
            <Button
              label={busy ? 'Iniciando…' : 'Confirmar e iniciar'}
              disabled={busy}
              onPress={() => onConfirm(draft)}
            />
          </View>
          <Text style={styles.muted}>
            {draft === INHERITED_IDENTIFICATION_MODE
              ? 'Se usará la configuración heredada del pasillo, inventario o cliente.'
              : `Se enviará el modo ${draft} al iniciar el trabajo.`}
          </Text>
        </View>
      </View>
    </Modal>
  );
}
