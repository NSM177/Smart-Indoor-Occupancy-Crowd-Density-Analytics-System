import { apiClient } from '../lib/axios';
import { AlertEntity } from '../types';

export interface AlertFilterParams {
  room_id?: string;
  severity?: string;
  only_unresolved?: boolean;
  limit?: number;
}

export const alertService = {
  async getAlerts(params?: AlertFilterParams): Promise<AlertEntity[]> {
    const { data } = await apiClient.get<AlertEntity[]>('/alerts', { params });
    return data;
  },

  async getAlertById(alertId: string): Promise<AlertEntity> {
    const { data } = await apiClient.get<AlertEntity>(`/alerts/${alertId}`);
    return data;
  },

  async acknowledgeAlert(alertId: string): Promise<AlertEntity> {
    const { data } = await apiClient.patch<AlertEntity>(
      `/alerts/${alertId}/acknowledge`,
    );
    return data;
  },

  async resolveAlert(alertId: string): Promise<AlertEntity> {
    const { data } = await apiClient.patch<AlertEntity>(
      `/alerts/${alertId}/resolve`,
    );
    return data;
  },
};
