import { create } from 'zustand';
import { useShallow } from 'zustand/react/shallow';
import {
  AlertEntity,
  SeverityLevel,
  WsConnectionStatus,
} from '../types';

export interface RealtimeZoneMetric {
  zoneCode: string;
  zoneName?: string;
  count: number;
  areaSqm: number;
  maxCapacity: number;
  densityPerSqm: number;
  capacityRatio: number;
  severity: SeverityLevel;
}

export interface LiveRoomTelemetry {
  room_id: string;
  room_code: string;
  room_name?: string;
  current_count: number;
  in_count: number;
  out_count: number;
  overall_density: number;
  capacity_ratio: number;
  room_status: SeverityLevel;
  inference_fps?: number | null;
  zones?: RealtimeZoneMetric[];
  updated_at: string;
}

/** Scalar KPIs of a live room; compared shallowly so pages only re-render on change. */
export type LiveRoomMetrics = Pick<
  LiveRoomTelemetry,
  | 'current_count'
  | 'in_count'
  | 'out_count'
  | 'overall_density'
  | 'capacity_ratio'
  | 'room_status'
  | 'inference_fps'
>;

interface RealtimeState {
  connectionStatus: WsConnectionStatus;
  lastMessageAt: number | null;
  isStale: boolean;
  liveRooms: Record<string, LiveRoomTelemetry>;
  /** Heatmap grids from the opt-in `heatmap.updated` stream, keyed by room id and code */
  liveHeatmaps: Record<string, number[][]>;
  liveAlerts: AlertEntity[];
  unreadAlertCount: number;
  setConnectionStatus: (status: WsConnectionStatus) => void;
  updateRoomOccupancy: (roomId: string, payload: Partial<LiveRoomTelemetry>) => void;
  updateHeatmap: (roomKeys: string[], grid: number[][]) => void;
  pushLiveAlert: (alert: AlertEntity) => void;
  markAlertsRead: () => void;
  checkStale: (maxAgeMs?: number) => void;
}

export const useRealtimeStore = create<RealtimeState>((set, get) => ({
  connectionStatus: 'DISCONNECTED',
  lastMessageAt: null,
  isStale: false,
  liveRooms: {},
  liveHeatmaps: {},
  liveAlerts: [],
  unreadAlertCount: 0,

  setConnectionStatus: (status) => set({ connectionStatus: status }),

  updateRoomOccupancy: (roomKey, payload) => {
    const now = Date.now();
    set((state) => {
      const existing = state.liveRooms[roomKey] || {
        room_id: payload.room_id || roomKey,
        room_code: payload.room_code || roomKey,
        current_count: 0,
        in_count: 0,
        out_count: 0,
        overall_density: 0,
        capacity_ratio: 0,
        room_status: 'NORMAL' as SeverityLevel,
        updated_at: new Date().toISOString(),
      };
      const merged: LiveRoomTelemetry = {
        ...existing,
        ...payload,
        updated_at: payload.updated_at || new Date().toISOString(),
      };
      const nextMap = { ...state.liveRooms, [roomKey]: merged };
      if (merged.room_code) {
        nextMap[merged.room_code] = merged;
      }
      if (merged.room_id) {
        nextMap[merged.room_id] = merged;
      }
      return {
        liveRooms: nextMap,
        lastMessageAt: now,
        isStale: false,
      };
    });
  },

  updateHeatmap: (roomKeys, grid) =>
    set((state) => {
      const next = { ...state.liveHeatmaps };
      roomKeys.forEach((key) => {
        if (key) next[key] = grid;
      });
      return { liveHeatmaps: next };
    }),

  pushLiveAlert: (alert) =>
    set((state) => {
      const exists = state.liveAlerts.some((a) => a.id === alert.id);
      if (exists) return state;
      return {
        liveAlerts: [alert, ...state.liveAlerts].slice(0, 50),
        unreadAlertCount: state.unreadAlertCount + 1,
        lastMessageAt: Date.now(),
        isStale: false,
      };
    }),

  markAlertsRead: () => set({ unreadAlertCount: 0 }),

  checkStale: (maxAgeMs = 30_000) => {
    const last = get().lastMessageAt;
    if (!last) return;
    const stale = Date.now() - last > maxAgeMs;
    if (stale !== get().isStale) {
      set({ isStale: stale });
    }
  },
}));

/**
 * Subscribe to the scalar KPIs of one live room. Unlike selecting
 * `liveRooms[roomKey]` (a new object on every WebSocket frame), this only
 * re-renders the caller when one of the displayed values actually changes.
 */
export function useLiveRoomMetrics(roomKey: string): LiveRoomMetrics | null {
  return useRealtimeStore(
    useShallow((s) => {
      const room = s.liveRooms[roomKey];
      if (!room) return null;
      return {
        current_count: room.current_count,
        in_count: room.in_count,
        out_count: room.out_count,
        overall_density: room.overall_density,
        capacity_ratio: room.capacity_ratio,
        room_status: room.room_status,
        inference_fps: room.inference_fps,
      };
    }),
  );
}
