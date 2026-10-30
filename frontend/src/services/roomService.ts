import { apiClient } from '../lib/axios';
import {
  RoomCreatePayload,
  RoomEntity,
  RoomUpdatePayload,
  ZoneCreatePayload,
  ZoneEntity,
  ZoneUpdatePayload,
} from '../types';

export const roomService = {
  async getRooms(): Promise<RoomEntity[]> {
    const { data } = await apiClient.get<RoomEntity[]>('/rooms');
    return data;
  },

  async getRoomById(roomId: string): Promise<RoomEntity> {
    const { data } = await apiClient.get<RoomEntity>(`/rooms/${roomId}`);
    return data;
  },

  async createRoom(payload: RoomCreatePayload): Promise<RoomEntity> {
    const { data } = await apiClient.post<RoomEntity>('/rooms', payload);
    return data;
  },

  async updateRoom(
    roomId: string,
    payload: RoomUpdatePayload,
  ): Promise<RoomEntity> {
    const { data } = await apiClient.put<RoomEntity>(
      `/rooms/${roomId}`,
      payload,
    );
    return data;
  },

  async deleteRoom(roomId: string): Promise<{ deleted: boolean; id: string }> {
    const { data } = await apiClient.delete<{ deleted: boolean; id: string }>(
      `/rooms/${roomId}`,
    );
    return data;
  },

  async getZonesByRoom(roomId: string): Promise<ZoneEntity[]> {
    const { data } = await apiClient.get<ZoneEntity[]>(
      `/rooms/${roomId}/zones`,
    );
    return data;
  },

  async createZone(
    roomId: string,
    payload: ZoneCreatePayload,
  ): Promise<ZoneEntity> {
    const { data } = await apiClient.post<ZoneEntity>(
      `/rooms/${roomId}/zones`,
      payload,
    );
    return data;
  },

  async updateZone(
    zoneId: string,
    payload: ZoneUpdatePayload,
  ): Promise<ZoneEntity> {
    const { data } = await apiClient.put<ZoneEntity>(
      `/zones/${zoneId}`,
      payload,
    );
    return data;
  },

  async deleteZone(zoneId: string): Promise<{ deleted: boolean; id: string }> {
    const { data } = await apiClient.delete<{ deleted: boolean; id: string }>(
      `/zones/${zoneId}`,
    );
    return data;
  },
};
