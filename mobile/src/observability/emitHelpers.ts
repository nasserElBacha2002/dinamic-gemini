import { compressionRatio, normalizeNetworkType } from './metrics';
import type { ObservabilityAttributeValue, ObservabilityEvent, ObservabilityReporter } from './types';
import { wallTimestamp } from './clock';
import type { ConnectivityService } from '../services/connectivity/connectivity';

export const TRANSFORMATION_VERSION = 'phase0-v1';

type LooseObsEvent = {
  readonly name: string;
  readonly timestamp?: string | undefined;
  readonly sessionId?: string | null | undefined;
  readonly localJobId?: string | null | undefined;
  readonly serverJobId?: string | null | undefined;
  readonly clientFileId?: string | null | undefined;
  readonly batchId?: string | null | undefined;
  readonly attemptId?: string | null | undefined;
  readonly durationMs?: number | null | undefined;
  readonly attributes?: Readonly<Record<string, ObservabilityAttributeValue>> | undefined;
};

function compactEvent(event: LooseObsEvent): ObservabilityEvent {
  const out: {
    name: string;
    timestamp: string;
    sessionId?: string;
    localJobId?: string;
    serverJobId?: string;
    clientFileId?: string;
    batchId?: string;
    attemptId?: string;
    durationMs?: number;
    attributes?: Record<string, ObservabilityAttributeValue>;
  } = {
    name: event.name,
    timestamp: event.timestamp ?? wallTimestamp(),
  };
  if (event.sessionId) out.sessionId = event.sessionId;
  if (event.localJobId) out.localJobId = event.localJobId;
  if (event.serverJobId) out.serverJobId = event.serverJobId;
  if (event.clientFileId) out.clientFileId = event.clientFileId;
  if (event.batchId) out.batchId = event.batchId;
  if (event.attemptId) out.attemptId = event.attemptId;
  if (event.durationMs != null && Number.isFinite(event.durationMs)) {
    out.durationMs = event.durationMs;
  }
  if (event.attributes) {
    out.attributes = { ...event.attributes };
  }
  return out;
}

export function emitObservability(
  reporter: ObservabilityReporter | null | undefined,
  event: LooseObsEvent,
): void {
  if (!reporter) {
    return;
  }
  reporter.emit(compactEvent(event));
}

export function networkAttributesFromConnectivity(
  connectivity: ConnectivityService | null | undefined,
): {
  readonly network_type: string;
  readonly is_connected: boolean | null;
  readonly is_internet_reachable: boolean | null;
  readonly connection_type: string | null;
} {
  const snap = connectivity?.getSnapshot?.();
  if (!snap) {
    const state = connectivity?.getState?.() ?? 'unknown';
    const cellular = connectivity?.isCellular?.() ?? false;
    return {
      network_type: normalizeNetworkType({
        isConnected: state === 'offline' ? false : state === 'online' ? true : null,
        isCellular: cellular,
        type: cellular ? 'cellular' : null,
      }),
      is_connected: state === 'offline' ? false : state === 'online' ? true : null,
      is_internet_reachable: null,
      connection_type: cellular ? 'cellular' : null,
    };
  }
  return {
    network_type: normalizeNetworkType({
      isConnected: snap.isConnected,
      type: snap.connectionType,
      isCellular: snap.isCellular,
    }),
    is_connected: snap.isConnected,
    is_internet_reachable: snap.isInternetReachable,
    connection_type: snap.connectionType,
  };
}

export function prepareMetricAttributes(input: {
  readonly originalBytes: number | null;
  readonly preparedBytes: number | null;
  readonly originalWidth: number | null;
  readonly originalHeight: number | null;
  readonly preparedWidth: number | null;
  readonly preparedHeight: number | null;
  readonly transformationProfile: string;
  readonly convertedFromHeic: boolean;
}): Record<string, string | number | boolean | null> {
  return {
    original_bytes: input.originalBytes,
    prepared_bytes: input.preparedBytes,
    compression_ratio: compressionRatio(input.originalBytes, input.preparedBytes),
    original_width: input.originalWidth,
    original_height: input.originalHeight,
    prepared_width: input.preparedWidth,
    prepared_height: input.preparedHeight,
    transformation_profile: input.transformationProfile,
    transformation_version: TRANSFORMATION_VERSION,
    converted_from_heic: input.convertedFromHeic,
  };
}
