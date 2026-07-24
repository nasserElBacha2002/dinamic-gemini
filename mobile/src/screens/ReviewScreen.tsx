import { Text, View } from 'react-native';

import type { CaptureSnapshot } from '../features/capture/captureService';
import type { AppServices } from '../runtime/bootstrap/createAppServices';
import { Button, ErrorText, PhotoWorkList, SmallButton, countPhotos, messageOf, styles } from '../ui';

export interface ReviewScreenProps {
  services: AppServices;
  snapshot: CaptureSnapshot | null;
  onBack: () => void;
  /** Called when capture review gates pass; parent decides next screen. */
  onConfirm: (sessionId: string) => void;
  onError: (message: string | null) => void;
}

export function ReviewScreen({ services, snapshot, onBack, onConfirm, onError }: ReviewScreenProps) {
  const photos = snapshot?.photos ?? [];
  const counts = countPhotos(photos);
  const canConfirm = counts.waiting === 0 && counts.errors === 0;
  const context = snapshot?.context;
  return (
    <PhotoWorkList
      photos={photos}
      onExclude={(id) => void services.capture.exclude(id)}
      onReinclude={(id) => void services.capture.reincorporate(id)}
      header={
        <View>
          <SmallButton label="← Captura" onPress={onBack} />
          <Text style={styles.h2}>
            Revisión · {context?.inventoryName ?? 'Inventario'} / {context?.aisleName ?? 'Pasillo'}
          </Text>
          <Text style={styles.row}>
            Estables: {counts.stable} · Excluidas: {counts.excluded} · Errores: {counts.errors}
          </Text>
          {!canConfirm ? <ErrorText text="Resolvé errores o esperá validaciones antes de confirmar." /> : null}
          <Button
            label="Reintentar errores"
            disabled={counts.errors === 0}
            onPress={() => void services.capture.retryErrors()}
          />
          <Button
            label="Confirmar y continuar"
            disabled={!canConfirm}
            onPress={() => {
              const sessionId = snapshot?.session?.id;
              if (!sessionId) {
                onError('No se encontró la sesión de captura.');
                return;
              }
              onConfirm(sessionId);
            }}
          />
        </View>
      }
    />
  );
}
