import { AI_SERVICE_URL, apiClient } from '../lib/axios';

export type VideoSourceMode = 'default' | 'video' | 'browser';

export interface VideoSourceStatus {
  mode: VideoSourceMode;
  connected: boolean;
  fps: number;
  uploaded_video: string | null;
  default_source: string;
  max_upload_mb?: number;
}

export const videoSourceService = {
  async getStatus(): Promise<VideoSourceStatus> {
    const { data } = await apiClient.get<VideoSourceStatus>(
      `${AI_SERVICE_URL}/sources/current`,
    );
    return data;
  },

  async select(mode: VideoSourceMode): Promise<VideoSourceStatus> {
    const { data } = await apiClient.post<VideoSourceStatus>(
      `${AI_SERVICE_URL}/sources/select`,
      { mode },
    );
    return data;
  },

  async uploadVideo(
    file: File,
    onProgress?: (percent: number) => void,
  ): Promise<VideoSourceStatus> {
    const { data } = await apiClient.post<VideoSourceStatus>(
      `${AI_SERVICE_URL}/sources/video`,
      file,
      {
        params: { filename: file.name },
        headers: { 'Content-Type': 'application/octet-stream' },
        timeout: 0,
        onUploadProgress: (event) => {
          if (event.total) {
            onProgress?.(Math.round((event.loaded / event.total) * 100));
          }
        },
      },
    );
    return data;
  },
};
