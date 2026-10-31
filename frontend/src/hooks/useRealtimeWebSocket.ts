import { useEffect } from 'react';
import { wsClientSingleton } from '../lib/websocket';
import { useRealtimeStore } from '../stores/realtimeStore';
import { useUIStore } from '../stores/uiStore';

/**
 * Owns the WebSocket connection for the layout and exposes only the
 * connection/alert state the layout renders. Live room telemetry is read by
 * pages through `useLiveRoomMetrics`, so the layout does not re-render on
 * every telemetry frame.
 */
export function useRealtimeWebSocket() {
  const selectedRoomId = useUIStore((s) => s.selectedRoomId);
  const connectionStatus = useRealtimeStore((s) => s.connectionStatus);
  const isStale = useRealtimeStore((s) => s.isStale);
  const liveAlerts = useRealtimeStore((s) => s.liveAlerts);
  const unreadAlertCount = useRealtimeStore((s) => s.unreadAlertCount);

  useEffect(() => {
    wsClientSingleton.acquire(selectedRoomId);
    return () => {
      wsClientSingleton.release();
    };
    // Acquire once per mounted layout
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    wsClientSingleton.switchRoom(selectedRoomId);
  }, [selectedRoomId]);

  return {
    connectionStatus,
    isStale,
    liveAlerts,
    unreadAlertCount,
  };
}

/** Opt into the heatmap stream while mounted and return the room's latest grid. */
export function useLiveHeatmap(roomKey: string): number[][] | undefined {
  useEffect(() => {
    wsClientSingleton.acquireHeatmap();
    return () => {
      wsClientSingleton.releaseHeatmap();
    };
  }, []);
  return useRealtimeStore((s) => s.liveHeatmaps[roomKey]);
}
