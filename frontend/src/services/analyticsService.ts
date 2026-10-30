import { apiClient } from '../lib/axios';
import {
  AnalyticsOverview,
  DailyBucketPoint,
  ForecastData,
  HourlyBucketPoint,
  OccupancyRecord,
  PeakHourItem,
  RoomDensityCurrent,
} from '../types';

export interface AnalyticsOccupancySeriesResponse {
  room_id: string;
  room_code: string;
  granularity: 'hourly' | 'daily' | 'raw';
  count: number;
  series: Array<HourlyBucketPoint & DailyBucketPoint & OccupancyRecord>;
}

export interface AnalyticsDensitySeriesResponse {
  room_id: string;
  room_code: string;
  granularity: 'hourly' | 'daily' | 'raw';
  current: RoomDensityCurrent;
  series: Array<HourlyBucketPoint & DailyBucketPoint>;
}

export const analyticsService = {
  async getOverview(roomId: string, hours = 24): Promise<AnalyticsOverview> {
    const { data } = await apiClient.get<AnalyticsOverview>(
      '/analytics/overview',
      {
        params: { room_id: roomId, hours },
      },
    );
    return data;
  },

  async getPeakHours(roomId: string, days = 7): Promise<PeakHourItem[]> {
    const { data } = await apiClient.get<PeakHourItem[]>(
      '/analytics/peak-hours',
      {
        params: { room_id: roomId, days },
      },
    );
    return data;
  },

  async getOccupancySeries(params: {
    room_id: string;
    granularity?: 'hourly' | 'daily' | 'raw';
    hours?: number;
    days?: number;
    limit?: number;
  }): Promise<AnalyticsOccupancySeriesResponse> {
    const { data } = await apiClient.get<AnalyticsOccupancySeriesResponse>(
      '/analytics/occupancy',
      { params },
    );
    return data;
  },

  async getDensitySeries(params: {
    room_id: string;
    zone_id?: string;
    granularity?: 'hourly' | 'daily' | 'raw';
    hours?: number;
    days?: number;
    limit?: number;
  }): Promise<AnalyticsDensitySeriesResponse> {
    const { data } = await apiClient.get<AnalyticsDensitySeriesResponse>(
      '/analytics/density',
      { params },
    );
    return data;
  },

  async getForecast(roomId: string, horizonMinutes = 30): Promise<ForecastData> {
    const { data } = await apiClient.get<ForecastData>('/analytics/forecast', {
      params: { room_id: roomId, horizon_minutes: horizonMinutes },
    });
    return data;
  },
};
