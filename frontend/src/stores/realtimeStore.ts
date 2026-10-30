import { create } from 'zustand';
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
  heatmap_grid?: number[][];
  updated_at: string;
}

interface RealtimeState {
  connectionStatus: WsConnectionStatus;
  lastMessageAt: number | null;
  isStale: boolean;
  liveRooms: Record<string, LiveRoomTelemetry>;
  liveAlerts: AlertEntity[];
  unreadAlertCount: number;
  setConnectionStatus: (status: WsConnectionStatus) => void;
  updateRoomOccupancy: (roomId: string, payload: Partial<LiveRoomTelemetry>) => void;
  pushLiveAlert: (alert: AlertEntity) => void;
  markAlertsRead: () => void;
  checkStale: (maxAgeMs?: number) => void;
}

export const useRealtimeStore = create<RealtimeState>((set, get) => ({
  connectionStatus: 'DISCONNECTED',
  lastMessageAt: null,
  isStale: false,
  liveRooms: {},
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
