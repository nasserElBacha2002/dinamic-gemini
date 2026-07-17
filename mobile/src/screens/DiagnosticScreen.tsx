import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, FlatList, Share, Text, View } from 'react-native';

import type { HealthCheckResult } from '../features/support/healthChecks';
import type { AppServices } from '../runtime/bootstrap/createAppServices';
import { Button, Card, ErrorText, SmallButton, messageOf, styles } from '../ui';

export interface DiagnosticScreenProps {
  services: AppServices;
  onBack: () => void;
}

export function DiagnosticScreen({ services, onBack }: DiagnosticScreenProps) {
  const [checks, setChecks] = useState<readonly HealthCheckResult[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [storageHint, setStorageHint] = useState<string | null>(null);

  const run = useCallback(() => {
    setBusy(true);
    setError(null);
    void Promise.all([services.runHealthChecks(), services.getStorageStatus()])
      .then(([results, storage]) => {
        setChecks(results);
        setStorageHint(
          storage.freeBytes == null
            ? null
            : `Libre: ${Math.round(storage.freeBytes / (1024 * 1024))} MB${storage.lowSpace ? ' (bajo)' : ''}`,
        );
      })
      .catch((e) => setError(messageOf(e)))
      .finally(() => setBusy(false));
  }, [services]);

  useEffect(() => {
    run();
  }, [run]);

  return (
    <FlatList
      data={checks}
      keyExtractor={(c) => c.id}
      ListHeaderComponent={
        <View>
          <SmallButton label="← Inventarios" onPress={onBack} />
          <Text style={styles.h2}>Diagnóstico</Text>
          <Text style={styles.row}>
            v{services.config.versionName} ({services.config.versionCode}) · {services.config.gitSha} ·{' '}
            {services.config.environment}
          </Text>
          {storageHint ? <Text style={styles.notif}>{storageHint}</Text> : null}
          {error ? <ErrorText text={error} /> : null}
          {busy ? <ActivityIndicator color="#94d2bd" /> : null}
        </View>
      }
      renderItem={({ item: c }) => (
        <Card>
          <Text style={styles.cardTitle}>
            [{c.status}] {c.label}
          </Text>
          <Text style={styles.row}>{c.detail}</Text>
        </Card>
      )}
      ListFooterComponent={
        <View>
          <Button label="Reejecutar checks" disabled={busy} onPress={run} />
          <Button
            label="Exportar diagnóstico"
            disabled={busy}
            onPress={() => {
              setBusy(true);
              void services
                .exportDiagnostic()
                .then((bundle) =>
                  Share.share({
                    message: services.diagnosticShareText(bundle),
                    title: 'Dinamic diagnóstico',
                  }),
                )
                .catch((e) => setError(messageOf(e)))
                .finally(() => setBusy(false));
            }}
          />
          <Text style={styles.muted}>
            El export no incluye tokens, fotos ni API keys. Usalo para soporte operativo.
          </Text>
        </View>
      }
    />
  );
}
