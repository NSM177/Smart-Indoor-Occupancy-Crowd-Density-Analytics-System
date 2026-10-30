import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { useAuthStore } from '../stores/authStore';
import { TokenResponse } from '../types';

export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:4000/api/v1';

export const WS_URL: string =
  import.meta.env.VITE_WS_URL || 'ws://localhost:4000/ws/realtime';

export const AI_SERVICE_URL: string =
  import.meta.env.VITE_AI_SERVICE_URL || 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15_000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request Interceptor: Attach JWT Bearer Token
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = useAuthStore.getState().accessToken;
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

let isRefreshing = false;
let pendingQueue: Array<{
  resolve: (token: string) => void;
  reject: (err: unknown) => void;
}> = [];

function processPendingQueue(error: unknown, token: string | null = null): void {
  pendingQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else if (token) {
      prom.resolve(token);
    }
  });
  pendingQueue = [];
}

// Response Interceptor: Centralized Error Normalization + Refresh Token Rotation
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<{ message?: string | string[]; detail?: string | string[] }>) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    if (
      error.response?.status === 401 &&
      originalRequest &&
      !originalRequest._retry &&
      !originalRequest.url?.includes('/auth/login') &&
      !originalRequest.url?.includes('/auth/refresh')
    ) {
      const refreshToken = useAuthStore.getState().refreshToken;
      if (refreshToken) {
        if (isRefreshing) {
          return new Promise<string>((resolve, reject) => {
            pendingQueue.push({ resolve, reject });
          }).then((newToken) => {
            if (originalRequest.headers) {
              originalRequest.headers.Authorization = `Bearer ${newToken}`;
            }
            return apiClient(originalRequest);
          });
        }

        originalRequest._retry = true;
        isRefreshing = true;

        try {
          const res = await axios.post<TokenResponse>(
            `${API_BASE_URL}/auth/refresh`,
            { refresh_token: refreshToken },
          );
          const { access_token, refresh_token, user } = res.data;
          useAuthStore.getState().setSession(access_token, refresh_token, user);
          processPendingQueue(null, access_token);
          if (originalRequest.headers) {
            originalRequest.headers.Authorization = `Bearer ${access_token}`;
          }
          return apiClient(originalRequest);
        } catch (refreshError) {
          processPendingQueue(refreshError, null);
          useAuthStore.getState().clearSession();
          return Promise.reject(extractApiErrorMessage(refreshError));
        } finally {
          isRefreshing = false;
        }
      } else {
        useAuthStore.getState().clearSession();
      }
    }

    return Promise.reject(new Error(extractApiErrorMessage(error)));
  },
);

export function extractApiErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as
      | { message?: string | string[]; detail?: string | string[] }
      | undefined;
    const rawMsg = data?.message ?? data?.detail;
    if (Array.isArray(rawMsg)) {
      return rawMsg.join('; ');
    }
    if (typeof rawMsg === 'string' && rawMsg.trim()) {
      return rawMsg;
    }
    if (error.message) {
      return error.message;
    }
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'Đã xảy ra lỗi kết nối tới máy chủ Backend.';
}
