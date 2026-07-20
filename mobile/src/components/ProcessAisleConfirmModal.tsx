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
  /** Session preference: null = inherit. */
  preference: AisleIdentificationMode | null;
  busy: boolean;
  error: string | null;
  onPreferenceChange: (next: AisleIdentificationMode | null) => void;
  onClose: () => void;
  onConfirm: () => void;
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
  onPreferenceChange,
  onClose,
  onConfirm,
}: ProcessAisleConfirmModalProps) {
  const [selection, setSelection] = useState<IdentificationModeSelection>(
    selectionFromPreference(preference),
  );

  useEffect(() => {
    if (!visible) return;
    setSelection(selectionFromPreference(preference));
  }, [visible, preference]);

  const selectedLabel = labelForIdentificationMode(preferenceFromSelection(selection));

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
            const active = selection === option.value;
            return (
              <TouchableOpacity
                key={option.value}
                accessibilityRole="radio"
                accessibilityState={{ selected: active, disabled: busy }}
                accessibilityLabel={`${option.label}. ${option.description}`}
                disabled={busy}
                style={[styles.pickerItem, active ? styles.pickerItemActive : null]}
                onPress={() => {
                  setSelection(option.value);
                  onPreferenceChange(preferenceFromSelection(option.value));
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
              onPress={onConfirm}
            />
          </View>
          <Text style={styles.muted}>
            {selection === INHERITED_IDENTIFICATION_MODE
              ? 'Se usará la configuración heredada del pasillo, inventario o cliente.'
              : `Se enviará el modo ${selection} al iniciar el trabajo.`}
          </Text>
        </View>
      </View>
    </Modal>
  );
}
