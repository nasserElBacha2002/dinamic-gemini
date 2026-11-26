import { useCallback, useEffect, useState } from 'react';
import {
  listLiveStreamChannels,
  type LiveStreamChannelSummary,
} from '../../api/liveStreamApi';

const POLL_MS = 8000;

export function useInventoryLiveStreamChannels(inventoryId: string, enabled: boolean) {
  const [channels, setChannels] = useState<LiveStreamChannelSummary[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!inventoryId) return;
    setLoading(true);
    try {
      const items = await listLiveStreamChannels(inventoryId);
      setChannels(items);
    } catch {
      setChannels([]);
    } finally {
      setLoading(false);
    }
  }, [inventoryId]);

  useEffect(() => {
    if (!enabled || !inventoryId) {
      setChannels([]);
      return undefined;
    }
    void refresh();
    const timer = window.setInterval(() => {
      void refresh();
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [enabled, inventoryId, refresh]);

  return { channels, loading, refresh };
}