import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Alert, View } from 'react-native';

import type { AppServices } from './src/runtime/bootstrap/createAppServices';
import { createAppServices } from './src/runtime/bootstrap/createAppServices';
import type { CaptureSnapshot } from './src/features/capture/captureService';
import type { AuthSession } from './src/features/auth/authService';
import type { AisleDto, InventoryListItemDto } from './src/services/api/types';
import type { CaptureSessionRow } from './src/database/schema/captureSchema';
import { findExclusiveCapture, type LocalAisleWork } from './src/features/capture/localAisleWork';
import type { UploadSessionProgress } from './src/features/upload/uploadQueue';
import { userMessageForCode } from './src/core/errorCatalog';
import { AislesScreen } from './src/screens/AislesScreen';
import { CaptureScreen } from './src/screens/CaptureScreen';
import { DiagnosticScreen } from './src/screens/DiagnosticScreen';
import { InventoriesScreen } from './src/screens/InventoriesScreen';
import { LoginScreen } from './src/screens/LoginScreen';
import { ProcessingScreen } from './src/screens/ProcessingScreen';
import { ResultsScreen } from './src/screens/ResultsScreen';
import { ReviewScreen } from './src/screens/ReviewScreen';
import { LocalResultReviewScreen } from './src/screens/LocalResultReviewScreen';
import { AuthoritativeFinalizeScreen } from './src/screens/AuthoritativeFinalizeScreen';
import { ServerReprocessScreen } from './src/screens/ServerReprocessScreen';
import { UploadsScreen } from './src/screens/UploadsScreen';
import type { AisleIdentificationMode } from './src/features/processing/processingMode';
import { sanitizeIdentificationModeSelection } from './src/features/processing/processingMode';
import { processingRunStore } from './src/features/processing/processingRun';
import { ErrorText, Shell, SmallButton, messageOf, styles } from './src/ui';

type Screen =
  | 'login'
  | 'inventories'
  | 'aisles'
  | 'capture'
  | 'review'
  | 'local-result-review'
  | 'uploads'
  | 'authoritative-finalize'
  | 'server-reprocess'
  | 'processing'
  | 'results'
  | 'diagnostic';

export default function App(): JSX.Element {
  const [services, setServices] = useState<AppServices | null>(null);
  const [screen, setScreen] = useState<Screen>('login');
  const [auth, setAuth] = useState<AuthSession | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedInventory, setSelectedInventory] = useState<InventoryListItemDto | null>(null);
  const [selectedAisle, setSelectedAisle] = useState<AisleDto | null>(null);
  const [capture, setCapture] = useState<CaptureSnapshot | null>(null);
  const [workSessionId, setWorkSessionId] = useState<string | null>(null);
  const [identificationModePreference, setIdentificationModePreference] =
    useState<AisleIdentificationMode | null>(null);
  const [connectivity, setConnectivity] = useState<'online' | 'offline' | 'unknown'>('unknown');
  const [localSessions, setLocalSessions] = useState<CaptureSessionRow[]>([]);
  const [uploadProgress, setUploadProgress] = useState<readonly UploadSessionProgress[]>([]);

  useEffect(() => {
    let mounted = true;
    let unsubscribeCapture: (() => void) | undefined;
    let unsubscribeConnectivity: (() => void) | undefined;
    let unsubscribeUpload: (() => void) | undefined;
    let createdServices: AppServices | undefined;
    void createAppServices(() => {
      processingRunStore.clear();
      setIdentificationModePreference(null);
      setAuth(null);
      setScreen('login');
      void createdServices?.uploadQueue.pause('auth');
    })
      .then(async (created) => {
        if (!mounted) return;
        createdServices = created;
        setServices(created);
        setConfigError(created.configError);
        if (
          created.config.flags.mobileLocalCodeScan ||
          created.config.flags.mobileAuthoritativeLocalCodeScan
        ) {
          setIdentificationModePreference('CODE_SCAN');
        }
        unsubscribeConnectivity = created.connectivity.subscribe((state) => {
          if (mounted) setConnectivity(state);
        });
        unsubscribeUpload = created.uploadQueue.subscribe((snap) => {
          if (mounted) setUploadProgress(snap.sessions);
        });
        const restored = created.configError ? null : await created.auth.restore();
        if (!mounted) return;
        setAuth(restored);
        const open = await created.capture.restoreLatestOpen();
        const activity = await created.capture.listActivitySessions();
        if (mounted) setLocalSessions(activity);
        unsubscribeCapture = created.capture.subscribe((snapshot) => {
          if (mounted) setCapture(snapshot);
        });
        if (restored) {
          routeAfterRestore(open, created, setScreen, setWorkSessionId, setSelectedInventory, setSelectedAisle);
        }
        setLoading(false);
      })
      .catch((e) => {
        setError(messageOf(e));
        setLoading(false);
      });
    return () => {
      mounted = false;
      unsubscribeCapture?.();
      unsubscribeConnectivity?.();
      unsubscribeUpload?.();
      void createdServices?.dispose();
    };
  }, []);

  const refreshLocalWork = useCallback(() => {
    if (!services) return;
    void services.capture.listActivitySessions().then(setLocalSessions);
  }, [services]);

  const hydrateSelection = useCallback(
    (inventoryId: string, aisleId: string, aisleName: string) => {
      if (!services) return;
      void services.inventories
        .getById(inventoryId)
        .then((inv) => setSelectedInventory(inv))
        .catch(() => {
          // keep navigation fallback already set
        });
      void services.aisles
        .getById(inventoryId, aisleId)
        .then((aisle) => setSelectedAisle(aisle))
        .catch(() => {
          setSelectedAisle((prev) =>
            prev ?? {
              id: aisleId,
              inventory_id: inventoryId,
              code: aisleName,
              status: 'created',
              created_at: '',
              updated_at: '',
              is_active: true,
              assets_count: 0,
              positions_count: 0,
              pending_review_positions_count: 0,
            },
          );
        });
    },
    [services],
  );

  useEffect(() => {
    if (!services || !auth) return;
    refreshLocalWork();
    const t = setInterval(refreshLocalWork, 4000);
    return () => clearInterval(t);
  }, [services, auth, refreshLocalWork, screen]);

  if (loading || !services) {
    return (
      <Shell title="Dinamic Captura">
        <ActivityIndicator color="#94d2bd" />
      </Shell>
    );
  }

  if (configError) {
    return (
      <Shell title="Configuración">
        <ErrorText text={configError} />
      </Shell>
    );
  }

  if (!auth || screen === 'login') {
    return (
      <LoginScreen
        services={services}
        onLoggedIn={(session) => {
          setAuth(session);
          setScreen('inventories');
          void services.uploadQueue.resume();
        }}
      />
    );
  }

  const openAisleWork = (work: LocalAisleWork, inventory: InventoryListItemDto | null) => {
    setWorkSessionId(work.sessionId);
    if (inventory) {
      setSelectedInventory(inventory);
    } else {
      setSelectedInventory({
        id: work.inventoryId,
        name: work.inventoryName ?? 'Inventario',
        status: 'draft',
        client_id: null,
        created_at: null,
        updated_at: null,
        aisles_count: 0,
        pending_review_count: 0,
        last_activity_at: null,
        processing_mode: 'production',
      });
    }
    setSelectedAisle({
      id: work.aisleId,
      inventory_id: work.inventoryId,
      code: work.aisleName,
      status: 'created',
      created_at: '',
      updated_at: '',
      is_active: true,
      assets_count: 0,
      positions_count: 0,
      pending_review_positions_count: 0,
    });
    hydrateSelection(work.inventoryId, work.aisleId, work.aisleName);
    if (
      services &&
      (services.config.flags.mobileLocalCodeScan ||
        services.config.flags.mobileAuthoritativeLocalCodeScan)
    ) {
      void services.uploadQueue.setSessionPreparationMode(work.sessionId, 'CODE_SCAN');
    }
    if (work.kind === 'capture_active' || work.kind === 'capture_paused') {
      void services.capture.loadSession(work.sessionId, work.kind === 'capture_active');
      setScreen('capture');
    } else if (work.kind === 'capture_review') {
      void services.capture.loadSession(work.sessionId, false);
      setScreen('review');
    } else if (work.kind === 'uploading' || work.kind === 'ready_to_process') {
      setScreen('uploads');
    } else if (work.kind === 'completed') {
      setScreen('results');
    } else {
      setScreen('processing');
    }
  };

  return (
    <Shell
      title="Dinamic Captura"
      footer={
        <View style={styles.nav}>
          <SmallButton label="Inventarios" onPress={() => setScreen('inventories')} />
          <SmallButton label="Diagnóstico" onPress={() => setScreen('diagnostic')} />
          <SmallButton
            label="Salir"
            onPress={() =>
              void services.auth.logout().finally(() => {
                processingRunStore.clear();
                setIdentificationModePreference(null);
                setAuth(null);
                setScreen('login');
              })
            }
          />
        </View>
      }
    >
      {error ? <ErrorText text={error} /> : null}
      {connectivity === 'offline' ? <ErrorText text={userMessageForCode('NETWORK_OFFLINE')} /> : null}
      {screen === 'inventories' ? (
        <InventoriesScreen
          services={services}
          connectivity={connectivity}
          localSessions={localSessions}
          uploadProgress={uploadProgress}
          onSelect={(inventory) => {
            setSelectedInventory(inventory);
            setScreen('aisles');
          }}
          onOpenWork={(work) => openAisleWork(work, null)}
        />
      ) : null}
      {screen === 'aisles' && selectedInventory ? (
        <AislesScreen
          services={services}
          connectivity={connectivity}
          inventory={selectedInventory}
          localSessions={localSessions}
          uploadProgress={uploadProgress}
          exclusive={findExclusiveCapture(localSessions)}
          onBack={() => setScreen('inventories')}
          onSelectNew={(aisle) => {
            setSelectedAisle(aisle);
            setWorkSessionId(null);
            if (selectedInventory) {
              services.capture.prepareNewCapture({
                inventoryId: selectedInventory.id,
                inventoryName: selectedInventory.name,
                aisleId: aisle.id,
                aisleName: aisle.code,
              });
            }
            setScreen('capture');
          }}
          onOpenWork={(work) => openAisleWork(work, selectedInventory)}
          onCancelCapture={() =>
            Alert.alert('Cancelar captura', 'No se borran fotos del teléfono.', [
              { text: 'No' },
              {
                text: 'Cancelar captura',
                style: 'destructive',
                onPress: () => void services.capture.cancel().then(refreshLocalWork),
              },
            ])
          }
        />
      ) : null}
      {screen === 'capture' && (capture?.context || (selectedInventory && selectedAisle)) ? (
        <CaptureScreen
          services={services}
          inventory={selectedInventory}
          aisle={selectedAisle}
          snapshot={capture}
          onReview={() => setScreen('review')}
          onBackToAisles={() => setScreen(selectedInventory ? 'aisles' : 'inventories')}
          onError={setError}
        />
      ) : null}
      {screen === 'review' ? (
        <ReviewScreen
          services={services}
          snapshot={capture}
          onBack={() => setScreen('capture')}
          onConfirm={(sessionId) => {
            setWorkSessionId(sessionId);
            const useLocalReview =
              services.config.flags.mobileAuthoritativeLocalCodeScan &&
              services.config.flags.mobileLocalResultReview;
            if (useLocalReview) {
              setScreen('local-result-review');
              return;
            }
            void services.capture
              .completeReview()
              .then((sid) => {
                setWorkSessionId(sid);
                if (identificationModePreference) {
                  void services.uploadQueue.setSessionPreparationMode(
                    sid,
                    identificationModePreference,
                  );
                }
                void services.uploadQueue.enqueueSession(sid);
                setScreen('uploads');
              })
              .catch((e) => setError(messageOf(e)));
          }}
          onError={setError}
        />
      ) : null}
      {screen === 'local-result-review' && workSessionId && auth ? (
        <LocalResultReviewScreen
          services={services}
          sessionId={workSessionId}
          userId={auth.user.id}
          onBack={() => setScreen('review')}
          onDone={(sessionId) => {
            void services.capture
              .completeReview()
              .then((sid) => {
                setWorkSessionId(sid);
                if (identificationModePreference) {
                  void services.uploadQueue.setSessionPreparationMode(
                    sid,
                    identificationModePreference,
                  );
                }
                void services.uploadQueue.enqueueSession(sid);
                setScreen('uploads');
              })
              .catch((e) => setError(messageOf(e)));
          }}
          onError={setError}
        />
      ) : null}
      {screen === 'uploads' && workSessionId ? (
        <UploadsScreen
          services={services}
          sessionId={workSessionId}
          identificationModePreference={identificationModePreference}
          onIdentificationModePreferenceChange={(next) => {
            const sanitized = sanitizeIdentificationModeSelection(next);
            setIdentificationModePreference(sanitized);
            if (workSessionId && sanitized) {
              void services.uploadQueue.setSessionPreparationMode(workSessionId, sanitized);
            }
          }}
          onBack={() => setScreen(selectedInventory ? 'aisles' : 'inventories')}
          onProcess={() => setScreen('processing')}
          onError={setError}
          onLocalReview={() => setScreen('local-result-review')}
          onAuthoritativeFinalize={() => setScreen('authoritative-finalize')}
        />
      ) : null}
      {screen === 'authoritative-finalize' &&
      workSessionId &&
      selectedInventory &&
      selectedAisle ? (
        <AuthoritativeFinalizeScreen
          services={services}
          sessionId={workSessionId}
          inventoryId={selectedInventory.id}
          aisleId={selectedAisle.id}
          inventoryName={selectedInventory.name ?? ''}
          aisleName={selectedAisle.code ?? ''}
          onBack={() => setScreen('uploads')}
          onCompleted={() => setScreen('results')}
          onError={setError}
        />
      ) : null}
      {screen === 'processing' && workSessionId ? (
        <ProcessingScreen
          services={services}
          sessionId={workSessionId}
          inventoryName={selectedInventory?.name ?? ''}
          aisleName={selectedAisle?.code ?? ''}
          identificationModePreference={identificationModePreference}
          onIdentificationModePreferenceChange={(next) => {
            const sanitized = sanitizeIdentificationModeSelection(next);
            setIdentificationModePreference(sanitized);
            if (workSessionId && sanitized) {
              void services.uploadQueue.setSessionPreparationMode(workSessionId, sanitized);
            }
          }}
          onBack={() => setScreen(selectedInventory ? 'aisles' : 'inventories')}
          onAnotherAisle={() => setScreen('inventories')}
          onViewResults={() => setScreen('results')}
          onError={setError}
        />
      ) : null}
      {screen === 'results' && workSessionId ? (
        <ResultsScreen
          services={services}
          sessionId={workSessionId}
          inventory={selectedInventory}
          aisle={selectedAisle}
          onBackToAisles={() => setScreen(selectedInventory ? 'aisles' : 'inventories')}
          onAnotherAisle={() => setScreen('inventories')}
          onServerReprocess={() => setScreen('server-reprocess')}
          onError={setError}
        />
      ) : null}
      {screen === 'server-reprocess' && selectedInventory && selectedAisle ? (
        <ServerReprocessScreen
          services={services}
          inventory={selectedInventory}
          aisle={selectedAisle}
          onBack={() => setScreen('results')}
          onError={setError}
        />
      ) : null}
      {screen === 'diagnostic' ? (
        <DiagnosticScreen services={services} onBack={() => setScreen('inventories')} />
      ) : null}
    </Shell>
  );
}

function routeAfterRestore(
  open: CaptureSessionRow | null,
  services: AppServices,
  setScreen: (s: Screen) => void,
  setWorkSessionId: (id: string | null) => void,
  setSelectedInventory: (i: InventoryListItemDto | null) => void,
  setSelectedAisle: (a: AisleDto | null) => void,
): void {
  if (!open) {
    setScreen('inventories');
    return;
  }
  setWorkSessionId(open.id);
  setSelectedInventory({
    id: open.inventory_id,
    name: open.inventory_name,
    status: 'draft',
    client_id: null,
    created_at: null,
    updated_at: null,
    aisles_count: 0,
    pending_review_count: 0,
    last_activity_at: null,
    processing_mode: 'production',
  });
  setSelectedAisle({
    id: open.aisle_id,
    inventory_id: open.inventory_id,
    code: open.aisle_name,
    status: 'created',
    created_at: '',
    updated_at: '',
    is_active: true,
    assets_count: 0,
    positions_count: 0,
    pending_review_positions_count: 0,
  });
  void services.inventories.getById(open.inventory_id).then(setSelectedInventory).catch(() => undefined);
  void services.aisles
    .getById(open.inventory_id, open.aisle_id)
    .then(setSelectedAisle)
    .catch(() => undefined);
  if (open.status === 'review') {
    setScreen('review');
  } else if (['uploading', 'upload_review', 'ready_to_process'].includes(open.status)) {
    setScreen('uploads');
  } else if (['processing', 'failed_processing'].includes(open.status)) {
    setScreen('processing');
  } else if (open.status === 'completed') {
    setScreen('results');
  } else {
    setScreen('capture');
  }
}
