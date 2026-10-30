import { apiClient } from '../lib/axios';
import { DeviceCommandPayload, DeviceEntity } from '../types';

export interface DeviceCommandResult {
  dispatched: boolean;
  mqtt_published: boolean;
  device: DeviceEntity;
  command: Record<string, unknown>;
}

export const deviceService = {
  async getDevices(roomId?: string): Promise<DeviceEntity[]> {
    const { data } = await apiClient.get<DeviceEntity[]>('/devices', {
      params: roomId ? { room_id: roomId } : undefined,
    });
    return data;
  },

  async getDeviceStatus(deviceId: string): Promise<DeviceEntity> {
    const { data } = await apiClient.get<DeviceEntity>(
      `/devices/${deviceId}/status`,
    );
    return data;
  },

  async sendCommand(
    deviceId: string,
    command: DeviceCommandPayload,
  ): Promise<DeviceCommandResult> {
    const { data } = await apiClient.post<DeviceCommandResult>(
      `/devices/${deviceId}/commands`,
      command,
    );
    return data;
  },
};
