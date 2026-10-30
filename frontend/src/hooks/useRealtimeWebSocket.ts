import { useEffect } from 'react';
import { wsClientSingleton } from '../lib/websocket';
import { useRealtimeStore } from '../stores/realtimeStore';
import { useUIStore } from '../stores/uiStore';

export function useRealtimeWebSocket() {
  const selectedRoomId = useUIStore((s) => s.selectedRoomId);
  const connectionStatus = useRealtimeStore((s) => s.connectionStatus);
  const isStale = useRealtimeStore((s) => s.isStale);
  const lastMessageAt = useRealtimeStore((s) => s.lastMessageAt);
  const liveRooms = useRealtimeStore((s) => s.liveRooms);
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

  const currentRoomLive = liveRooms[selectedRoomId] || null;

  return {
    connectionStatus,
    isStale,
    lastMessageAt,
    currentRoomLive,
    liveAlerts,
    unreadAlertCount,
  };
}
