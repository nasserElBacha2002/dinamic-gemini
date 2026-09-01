import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Alert, AppState, type AppStateStatus, View } from 'react-native';

import type { AppServices } from './src/runtime/bootstrap/createAppServices';
import { createAppServices } from './src/runtime/bootstrap/createAppServices';
import { shouldTriggerReconnectCatalogSync } from './src/features/catalog/catalogSyncPolicy';
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
import { AisleRevisionScreen } from './src/screens/AisleRevisionScreen';
import { AisleHistoryScreen } from './src/screens/AisleHistoryScreen';
import { UploadsScreen } from './src/screens/UploadsScreen';
import { ExcludedPhotosScreen } from './src/screens/ExcludedPhotosScreen';
import { AisleResultsListScreen } from './src/screens/AisleResultsListScreen';
import { LocalActivityScreen } from './src/screens/LocalActivityScreen';
import { ClientPositionLabelsScreen } from './src/screens/ClientPositionLabelsScreen';
import type { AisleIdentificationMode } from './src/features/processing/processingMode';
import { sanitizeIdentificationModeSelection } from './src/features/processing/processingMode';
import { processingRunStore } from './src/features/processing/processingRun';
import { ErrorText, Shell, SmallButton, messageOf, styles } from './src/ui';

async function finishReviewForExport(
  services: AppServices,
  sessionId: string,
  auth: AuthSession | null,
  capture: CaptureSnapshot | null,
): Promise<void> {
  if (services.config.flags.mobileAuthoritativeLocalCodeScan && auth?.user?.id) {
    const snap =
      capture?.session?.id === sessionId
        ? capture
        : await services.capture.loadSession(sessionId, false);
    await services.confirmLocalResult.confirmResolvedDraftsForSession({
      sessionId,
      confirmedByUserId: auth.user.id,
      photos: snap.photos,
    });
  }
  await services.capture.completeLocalSession({ uploadPolicy: 'MANUAL' });
  await services.capture.loadSession(sessionId, false);
}

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
  | 'aisle-revision'
  | 'aisle-history'
  | 'processing'
  | 'results'
  | 'aisle-results-list'
  | 'excluded-photos'
  | 'position-labels'
  | 'diagnostic'
  | 'local-activity';

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
  const [forceNewCapture, setForceNewCapture] = useState(false);
  const [footerHeight, setFooterHeight] = useState(72);

  useEffect(() => {
    let mounted = true;
    let unsubscribeCapture: (() => void) | undefined;
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
        if (created.databaseRecoveredFromCorruption) {
          Alert.alert(
            'Datos locales reiniciados',
            userMessageForCode('LOCAL_DB_CORRUPTED'),
          );
        }
        setIdentificationModePreference(null);
        unsubscribeUpload = created.uploadQueue.subscribe((snap) => {
          if (mounted) setUploadProgress(snap.sessions);
        });
        const startupConnectivity = created.connectivity.getState();
        if (mounted) setConnectivity(startupConnectivity);
        const restored = created.configError
          ? null
          : await created.auth.restore(startupConnectivity);
        if (!mounted) return;
        setAuth(restored);
        if (restored) {
          void created.catalog.bootstrap(startupConnectivity).catch(() => undefined);
        }
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
    if (!services) return;
    let mounted = true;
    let previous = services.connectivity.getState();
    const unsub = services.connectivity.subscribe((state) => {
      if (mounted) setConnectivity(state);
      if (shouldTriggerReconnectCatalogSync(Boolean(auth), previous, state)) {
        void services.catalog.requestSync('reconnect').catch(() => undefined);
      }
      previous = state;
    });
    return () => {
      mounted = false;
      unsub();
    };
  }, [services, auth]);

  useEffect(() => {
    if (!services || !auth) return;
    refreshLocalWork();
    const t = setInterval(refreshLocalWork, 4000);
    return () => clearInterval(t);
  }, [services, auth, refreshLocalWork, screen]);

  useEffect(() => {
    if (!services || !auth) return;
    const sub = AppState.addEventListener('change', (next: AppStateStatus) => {
      if (next === 'active' && connectivity !== 'offline') {
        void services.catalog.requestSync('foreground').catch(() => undefined);
      }
    });
    return () => sub.remove();
  }, [services, auth, connectivity]);

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
          if (services.config.flags.mobileServerUpload) {
            void services.uploadQueue.resume();
          }
          void services.catalog.bootstrap('online').catch(() => undefined);
          void services.catalog.requestSync('login').catch(() => undefined);
        }}
      />
    );
  }

  const serverUploadEnabled = services.config.flags.mobileServerUpload === true;

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
      serverUploadEnabled &&
      (services.config.flags.mobileLocalCodeScan ||
        services.config.flags.mobileAuthoritativeLocalCodeScan)
    ) {
      void services.uploadQueue.setSessionPreparationMode(work.sessionId, 'CODE_SCAN');
    }
    if (work.kind === 'capture_active' || work.kind === 'capture_paused') {
      setForceNewCapture(false);
      void services.capture.loadSession(work.sessionId, work.kind === 'capture_active');
      setScreen('capture');
    } else if (work.kind === 'capture_review' || work.kind === 'local_completed') {
      setForceNewCapture(false);
      void services.capture.loadSession(work.sessionId, false);
      setScreen('review');
    } else if (!serverUploadEnabled) {
      setForceNewCapture(false);
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
      contentPaddingBottom={footerHeight}
      footer={
        <View
          style={styles.nav}
          onLayout={(e) => {
            const h = e.nativeEvent.layout.height;
            if (h > 0 && Math.abs(h - footerHeight) > 1) {
              setFooterHeight(h);
            }
          }}
        >
          <SmallButton label="Inventarios" onPress={() => setScreen('inventories')} />
          <SmallButton label="Actividad local" onPress={() => setScreen('local-activity')} />
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
            setForceNewCapture(true);
            if (selectedInventory) {
              services.capture.prepareNewCapture(
                {
                  inventoryId: selectedInventory.id,
                  inventoryName: selectedInventory.name,
                  aisleId: aisle.id,
                  aisleName: aisle.code,
                },
                { forceClear: true },
              );
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
          {...(selectedInventory.client_id
            ? { onOpenPositionLabels: () => setScreen('position-labels') }
            : {})}
        />
      ) : null}
      {screen === 'position-labels' && selectedInventory?.client_id ? (
        <ClientPositionLabelsScreen
          services={services}
          clientId={selectedInventory.client_id}
          clientName={selectedInventory.name}
          onBack={() => setScreen('aisles')}
        />
      ) : null}
      {screen === 'capture' && (capture?.context || (selectedInventory && selectedAisle)) ? (
        <CaptureScreen
          services={services}
          inventory={selectedInventory}
          aisle={selectedAisle}
          snapshot={capture}
          forceNewCapture={forceNewCapture}
          onReview={() => {
            setForceNewCapture(false);
            setScreen('review');
          }}
          onBackToAisles={() => {
            setForceNewCapture(false);
            setScreen(selectedInventory ? 'aisles' : 'inventories');
          }}
          onError={setError}
        />
      ) : null}
      {screen === 'review' ? (
        <ReviewScreen
          services={services}
          snapshot={capture}
          onBack={() =>
            setScreen(
              capture?.session?.status === 'local_completed'
                ? 'local-activity'
                : 'capture',
            )
          }
          onConfirm={(sessionId) => {
            setWorkSessionId(sessionId);
            const useLocalReview =
              serverUploadEnabled &&
              services.config.flags.mobileAuthoritativeLocalCodeScan &&
              services.config.flags.mobileLocalResultReview;
            if (useLocalReview) {
              setScreen('local-result-review');
              return;
            }
            void (async () => {
              try {
                if (serverUploadEnabled) {
                  if (
                    services.config.flags.mobileAuthoritativeLocalCodeScan &&
                    auth?.user?.id
                  ) {
                    const snap =
                      capture?.session?.id === sessionId
                        ? capture
                        : await services.capture.loadSession(sessionId, false);
                    await services.confirmLocalResult.confirmResolvedDraftsForSession({
                      sessionId,
                      confirmedByUserId: auth.user.id,
                      photos: snap.photos,
                    });
                  }
                  const sid = await services.capture.completeReview();
                  setWorkSessionId(sid);
                  await services.uploadQueue.setSessionPreparationMode(sid, 'CODE_SCAN');
                  await services.uploadQueue.enqueueSession(sid);
                  setScreen('uploads');
                  return;
                }
                await finishReviewForExport(services, sessionId, auth, capture);
              } catch (e) {
                setError(messageOf(e));
              }
            })();
          }}
          onError={setError}
        />
      ) : null}
      {serverUploadEnabled && screen === 'local-result-review' && workSessionId && auth ? (
        <LocalResultReviewScreen
          services={services}
          sessionId={workSessionId}
          userId={auth.user.id}
          onBack={() => setScreen('review')}
          onDone={(_sessionId) => {
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
      {serverUploadEnabled && screen === 'uploads' && workSessionId ? (
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
          onViewAisleResults={() => setScreen('aisle-results-list')}
          onExcludedPhotos={() => setScreen('excluded-photos')}
        />
      ) : null}
      {serverUploadEnabled && screen === 'authoritative-finalize' &&
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
      {serverUploadEnabled && screen === 'processing' && workSessionId ? (
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
          onViewAisleResults={() => setScreen('aisle-results-list')}
          onExcludedPhotos={() => setScreen('excluded-photos')}
          onError={setError}
        />
      ) : null}
      {serverUploadEnabled && screen === 'aisle-results-list' && workSessionId ? (
        <AisleResultsListScreen
          services={services}
          sessionId={workSessionId}
          inventoryName={selectedInventory?.name ?? ''}
          aisleName={selectedAisle?.code ?? ''}
          onBack={() => setScreen('uploads')}
          onViewServerResult={() => setScreen('results')}
          onUploadLocal={() => undefined}
          onError={setError}
        />
      ) : null}
      {serverUploadEnabled && screen === 'excluded-photos' && workSessionId ? (
        <ExcludedPhotosScreen
          services={services}
          sessionId={workSessionId}
          inventoryName={selectedInventory?.name ?? ''}
          aisleName={selectedAisle?.code ?? ''}
          onBack={() => setScreen('uploads')}
          onError={setError}
        />
      ) : null}
      {serverUploadEnabled && screen === 'results' && workSessionId ? (
        <ResultsScreen
          services={services}
          sessionId={workSessionId}
          inventory={selectedInventory}
          aisle={selectedAisle}
          onBackToAisles={() => setScreen(selectedInventory ? 'aisles' : 'inventories')}
          onAnotherAisle={() => setScreen('inventories')}
          onServerReprocess={() => setScreen('server-reprocess')}
          onAisleRevision={() => setScreen('aisle-revision')}
          onAisleHistory={() => setScreen('aisle-history')}
          onError={setError}
        />
      ) : null}
      {serverUploadEnabled && screen === 'server-reprocess' && selectedInventory && selectedAisle ? (
        <ServerReprocessScreen
          services={services}
          inventory={selectedInventory}
          aisle={selectedAisle}
          onBack={() => setScreen('results')}
          onError={setError}
        />
      ) : null}
      {serverUploadEnabled && screen === 'aisle-revision' && selectedInventory && selectedAisle && auth ? (
        <AisleRevisionScreen
          services={services}
          inventory={selectedInventory}
          aisle={selectedAisle}
          userId={auth.user.id}
          onBack={() => setScreen('results')}
          {...(services.aisleRevision.isHistoryVisible()
            ? { onOpenHistory: () => setScreen('aisle-history') }
            : {})}
          onError={setError}
        />
      ) : null}
      {serverUploadEnabled && screen === 'aisle-history' && selectedInventory && selectedAisle && auth ? (
        <AisleHistoryScreen
          services={services}
          inventory={selectedInventory}
          aisle={selectedAisle}
          userId={auth.user.id}
          onBack={() => setScreen('aisle-revision')}
          onError={setError}
        />
      ) : null}
      {screen === 'diagnostic' ? (
        <DiagnosticScreen services={services} onBack={() => setScreen('inventories')} />
      ) : null}
      {screen === 'local-activity' ? (
        <LocalActivityScreen
          services={services}
          onBack={() => setScreen('inventories')}
          onError={setError}
          onOpenSession={(work) => {
            setWorkSessionId(work.sessionId);
            setForceNewCapture(false);
            if (work.kind === 'capture_active' || work.kind === 'capture_paused') {
              void services.capture.loadSession(work.sessionId, work.kind === 'capture_active');
              setScreen('capture');
              return;
            }
            if (work.kind === 'capture_review' || work.kind === 'local_completed') {
              void services.capture.loadSession(work.sessionId, false).then(() => {
                setScreen('review');
              });
              return;
            }
            if (!serverUploadEnabled) {
              void services.capture.loadSession(work.sessionId, false).then(() => {
                setScreen('review');
              });
              return;
            }
            setScreen('uploads');
          }}
        />
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
  } else if (
    services.config.flags.mobileServerUpload &&
    ['uploading', 'upload_review', 'ready_to_process'].includes(open.status)
  ) {
    setScreen('uploads');
  } else if (
    services.config.flags.mobileServerUpload &&
    ['processing', 'failed_processing'].includes(open.status)
  ) {
    setScreen('processing');
  } else if (services.config.flags.mobileServerUpload && open.status === 'completed') {
    setScreen('results');
  } else if (
    !services.config.flags.mobileServerUpload &&
    [
      'local_completed',
      'uploading',
      'upload_review',
      'ready_to_process',
      'processing',
      'failed_processing',
      'failed',
      'completed',
    ].includes(open.status)
  ) {
    void services.capture.loadSession(open.id, false);
    setScreen('review');
  } else {
    setScreen('capture');
  }
}
