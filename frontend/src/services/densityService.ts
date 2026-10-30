import axios from 'axios';
import { AI_SERVICE_URL, apiClient } from '../lib/axios';
import {
  AiEngineRealtimeAnalytics,
  DensityRecord,
  RoomDensityCurrent,
} from '../types';

export interface DensityHistoryQuery {
  zone_id?: string;
  start_time?: string;
  end_time?: string;
  limit?: number;
}

export const densityService = {
  async getCurrentDensity(roomId: string): Promise<RoomDensityCurrent> {
    const { data } = await apiClient.get<RoomDensityCurrent>(
      `/rooms/${roomId}/density/current`,
    );
    return data;
  },

  async getDensityHistory(
    roomId: string,
    params?: DensityHistoryQuery,
  ): Promise<DensityRecord[]> {
    const { data } = await apiClient.get<DensityRecord[]>(
      `/rooms/${roomId}/density/history`,
      { params },
    );
    return data;
  },

  async getAiEngineCurrent(): Promise<AiEngineRealtimeAnalytics | null> {
    try {
      const { data } = await axios.get<AiEngineRealtimeAnalytics>(
        `${AI_SERVICE_URL}/analytics/current`,
        { timeout: 3500 },
      );
      return data;
    } catch {
      return null;
    }
  },
};
