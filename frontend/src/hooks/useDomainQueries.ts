import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { alertService, AlertFilterParams } from '../services/alertService';
import { analyticsService } from '../services/analyticsService';
import { densityService, DensityHistoryQuery } from '../services/densityService';
import { deviceService } from '../services/deviceService';
import {
  occupancyService,
  OccupancyHistoryQuery,
} from '../services/occupancyService';
import { roomService } from '../services/roomService';
import {
  DeviceCommandPayload,
  RoomCreatePayload,
  RoomUpdatePayload,
  ZoneCreatePayload,
  ZoneUpdatePayload,
} from '../types';
import { useRealtimeStore } from '../stores/realtimeStore';

// Poll slowly while the WebSocket is delivering fresh data, fall back to the
// faster interval when it is disconnected or stale.
function realtimeAwareInterval(healthyMs: number, fallbackMs: number) {
  return () => {
    const { connectionStatus, isStale, lastMessageAt } =
      useRealtimeStore.getState();
    return connectionStatus === 'CONNECTED' && !isStale && lastMessageAt !== null
      ? healthyMs
      : fallbackMs;
  };
}

// ============================================================================
// Rooms & Polygon Zones Hooks
// ============================================================================
export function useRoomsQuery() {
  return useQuery({
    queryKey: ['rooms'],
    queryFn: () => roomService.getRooms(),
  });
}

export function useRoomDetailQuery(roomId: string) {
  return useQuery({
    queryKey: ['rooms', roomId],
    queryFn: () => roomService.getRoomById(roomId),
    enabled: Boolean(roomId),
  });
}

export function useRoomZonesQuery(roomId: string) {
  return useQuery({
    queryKey: ['zones', roomId],
    queryFn: () => roomService.getZonesByRoom(roomId),
    enabled: Boolean(roomId),
  });
}

export function useCreateRoomMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: RoomCreatePayload) => roomService.createRoom(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['rooms'] });
    },
  });
}

export function useUpdateRoomMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      roomId,
      payload,
    }: {
      roomId: string;
      payload: RoomUpdatePayload;
    }) => roomService.updateRoom(roomId, payload),
    onSuccess: (_, variables) => {
      qc.invalidateQueries({ queryKey: ['rooms'] });
      qc.invalidateQueries({ queryKey: ['rooms', variables.roomId] });
      qc.invalidateQueries({ queryKey: ['occupancy-current'] });
      qc.invalidateQueries({ queryKey: ['density-current'] });
    },
  });
}

export function useDeleteRoomMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (roomId: string) => roomService.deleteRoom(roomId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['rooms'] });
    },
  });
}

export function useCreateZoneMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      roomId,
      payload,
    }: {
      roomId: string;
      payload: ZoneCreatePayload;
    }) => roomService.createZone(roomId, payload),
    onSuccess: (_, variables) => {
      qc.invalidateQueries({ queryKey: ['rooms'] });
      qc.invalidateQueries({ queryKey: ['zones', variables.roomId] });
      qc.invalidateQueries({ queryKey: ['density-current'] });
    },
  });
}

export function useUpdateZoneMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      zoneId,
      payload,
    }: {
      zoneId: string;
      payload: ZoneUpdatePayload;
    }) => roomService.updateZone(zoneId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['rooms'] });
      qc.invalidateQueries({ queryKey: ['zones'] });
      qc.invalidateQueries({ queryKey: ['density-current'] });
    },
  });
}

export function useDeleteZoneMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (zoneId: string) => roomService.deleteZone(zoneId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['rooms'] });
      qc.invalidateQueries({ queryKey: ['zones'] });
      qc.invalidateQueries({ queryKey: ['density-current'] });
    },
  });
}

// ============================================================================
// Occupancy & Density Hooks
// ============================================================================
export function useCurrentOccupancyQuery(roomId: string) {
  return useQuery({
    queryKey: ['occupancy-current', roomId],
    queryFn: () => occupancyService.getCurrentOccupancy(roomId),
    enabled: Boolean(roomId),
    refetchInterval: realtimeAwareInterval(30_000, 8_000),
  });
}

export function useOccupancyHistoryQuery(
  roomId: string,
  params?: OccupancyHistoryQuery,
) {
  return useQuery({
    queryKey: ['occupancy-history', roomId, params],
    queryFn: () => occupancyService.getOccupancyHistory(roomId, params),
    enabled: Boolean(roomId),
    refetchInterval: 15_000,
  });
}

export function useCurrentDensityQuery(roomId: string) {
  return useQuery({
    queryKey: ['density-current', roomId],
    queryFn: () => densityService.getCurrentDensity(roomId),
    enabled: Boolean(roomId),
    refetchInterval: realtimeAwareInterval(30_000, 8_000),
  });
}

export function useDensityHistoryQuery(
  roomId: string,
  params?: DensityHistoryQuery,
) {
  return useQuery({
    queryKey: ['density-history', roomId, params],
    queryFn: () => densityService.getDensityHistory(roomId, params),
    enabled: Boolean(roomId),
    refetchInterval: 15_000,
  });
}

export function useAiEngineRealtimeQuery(enabled = true) {
  return useQuery({
    queryKey: ['ai-engine-current'],
    queryFn: () => densityService.getAiEngineCurrent(),
    enabled,
    refetchInterval: realtimeAwareInterval(15_000, 3_000),
  });
}

// ============================================================================
// Historical Analytics & Forecasting Hooks
// ============================================================================
export function useAnalyticsOverviewQuery(roomId: string, hours = 24) {
  return useQuery({
    queryKey: ['analytics-overview', roomId, hours],
    queryFn: () => analyticsService.getOverview(roomId, hours),
    enabled: Boolean(roomId),
    refetchInterval: 60_000,
  });
}

export function usePeakHoursQuery(roomId: string, days = 7) {
  return useQuery({
    queryKey: ['analytics-peak-hours', roomId, days],
    queryFn: () => analyticsService.getPeakHours(roomId, days),
    enabled: Boolean(roomId),
  });
}

export function useOccupancySeriesQuery(params: {
  room_id: string;
  granularity?: 'hourly' | 'daily' | 'raw';
  hours?: number;
  days?: number;
  limit?: number;
}) {
  return useQuery({
    queryKey: ['analytics-occupancy-series', params],
    queryFn: () => analyticsService.getOccupancySeries(params),
    enabled: Boolean(params.room_id),
  });
}

export function useDensitySeriesQuery(params: {
  room_id: string;
  zone_id?: string;
  granularity?: 'hourly' | 'daily' | 'raw';
  hours?: number;
  days?: number;
  limit?: number;
}) {
  return useQuery({
    queryKey: ['analytics-density-series', params],
    queryFn: () => analyticsService.getDensitySeries(params),
    enabled: Boolean(params.room_id),
  });
}

export function useForecastQuery(roomId: string, horizonMinutes = 30) {
  return useQuery({
    queryKey: ['analytics-forecast', roomId, horizonMinutes],
    queryFn: () => analyticsService.getForecast(roomId, horizonMinutes),
    enabled: Boolean(roomId),
    refetchInterval: 20_000,
  });
}

// ============================================================================
// Alerts & Devices Hooks
// ============================================================================
export function useAlertsQuery(params?: AlertFilterParams) {
  return useQuery({
    queryKey: ['alerts', params],
    queryFn: () => alertService.getAlerts(params),
    refetchInterval: realtimeAwareInterval(30_000, 10_000),
  });
}

export function useAcknowledgeAlertMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (alertId: string) => alertService.acknowledgeAlert(alertId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['alerts'] });
      qc.invalidateQueries({ queryKey: ['analytics-overview'] });
    },
  });
}

export function useResolveAlertMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (alertId: string) => alertService.resolveAlert(alertId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['alerts'] });
      qc.invalidateQueries({ queryKey: ['analytics-overview'] });
    },
  });
}

export function useDevicesQuery(roomId?: string) {
  return useQuery({
    queryKey: ['devices', roomId],
    queryFn: () => deviceService.getDevices(roomId),
    refetchInterval: realtimeAwareInterval(30_000, 10_000),
  });
}

export function useSendDeviceCommandMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      deviceId,
      command,
    }: {
      deviceId: string;
      command: DeviceCommandPayload;
    }) => deviceService.sendCommand(deviceId, command),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['devices'] });
    },
  });
}
