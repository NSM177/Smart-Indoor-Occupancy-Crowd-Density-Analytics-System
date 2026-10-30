import { apiClient } from '../lib/axios';
import { OccupancyCurrent, OccupancyRecord } from '../types';

export interface OccupancyHistoryQuery {
  start_time?: string;
  end_time?: string;
  limit?: number;
}

export const occupancyService = {
  async getCurrentOccupancy(roomId: string): Promise<OccupancyCurrent> {
    const { data } = await apiClient.get<OccupancyCurrent>(
      `/rooms/${roomId}/occupancy/current`,
    );
    return data;
  },

  async getOccupancyHistory(
    roomId: string,
    params?: OccupancyHistoryQuery,
  ): Promise<OccupancyRecord[]> {
    const { data } = await apiClient.get<OccupancyRecord[]>(
      `/rooms/${roomId}/occupancy/history`,
      { params },
    );
    return data;
  },
};
