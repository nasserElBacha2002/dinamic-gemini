import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../../api/types';
import {
  getLiveStreamStatus,
  getPreparedLiveStreamChannel,
  listLiveStreamChannels,
  type LiveStreamChannelSummary,
} from '../../api/liveStreamApi';
import { isApiNotPreparedError } from './liveStreamPresence';
import { addPreparedAisle, readPreparedAisles } from './liveStreamPreparedAisles';

const POLL_MS = 8000;

async function discoverPreparedAisles(inventoryId: string, aisleCodes: string[]): Promise<void> {
  await Promise.all(
    aisleCodes.map(async (code) => {
      try {
        const prepared = await getPreparedLiveStreamChannel(inventoryId, code);
        addPreparedAisle(inventoryId, prepared.canonical_aisle_code || code);
      } catch (error) {
        if (!isApiNotPreparedError(error)) {
          // ignore transient errors during discovery
        }
      }
    }),
  );
}

async function probeChannelsFromAisles(inventoryId: string): Promise<LiveStreamChannelSummary[]> {
  const codes = readPreparedAisles(inventoryId);
  if (codes.length === 0) return [];

  const results = await Promise.all(
    codes.map(async (code) => {
      try {
        const status = await getLiveStreamStatus(inventoryId, code);
        return {
          aisle_code: code,
          canonical_aisle_code: code,
          channel_slug: code,
          mediamtx_path: '',
          status,
        } satisfies LiveStreamChannelSummary;
      } catch {
        return null;
      }
    }),
  );
  return results.filter((r): r is LiveStreamChannelSummary => r !== null);
}

export function useInventoryLiveStreamChannels(
  inventoryId: string,
  enabled: boolean,
  aisleCodes: string[],
) {
  const [channels, setChannels] = useState<LiveStreamChannelSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const preferProbeRef = useRef(false);
  const discoverDoneRef = useRef(false);

  const refresh = useCallback(async () => {
    if (!inventoryId) return;
    setLoading(true);
    try {
      if (!preferProbeRef.current) {
        try {
          const items = await listLiveStreamChannels(inventoryId);
          setChannels(items);
          return;
        } catch (error) {
          if (error instanceof ApiError && error.status === 404) {
            preferProbeRef.current = true;
          } else if (error instanceof ApiError && error.status === 503) {
            setChannels([]);
            return;
          } else {
            throw error;
          }
        }
      }
      if (!discoverDoneRef.current && aisleCodes.length > 0) {
        await discoverPreparedAisles(inventoryId, aisleCodes);
        discoverDoneRef.current = true;
      }
      setChannels(await probeChannelsFromAisles(inventoryId));
    } catch {
      setChannels([]);
    } finally {
      setLoading(false);
    }
  }, [aisleCodes, inventoryId]);

  useEffect(() => {
    if (!enabled || !inventoryId) {
      setChannels([]);
      preferProbeRef.current = false;
      return undefined;
    }
    void refresh();
    const timer = window.setInterval(() => {
      void refresh();
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [enabled, inventoryId, refresh]);

  const notePreparedAisle = useCallback(
    (aisleCode: string) => {
      addPreparedAisle(inventoryId, aisleCode);
      void refresh();
    },
    [inventoryId, refresh],
  );

  return { channels, loading, refresh, notePreparedAisle };
}