import { apiClient } from '../lib/axios';
import {
  CreateUserPayload,
  LoginPayload,
  TokenResponse,
  UserProfile,
} from '../types';

export const authService = {
  async login(payload: LoginPayload): Promise<TokenResponse> {
    const { data } = await apiClient.post<TokenResponse>('/auth/login', payload);
    return data;
  },

  async refresh(refreshToken: string): Promise<TokenResponse> {
    const { data } = await apiClient.post<TokenResponse>('/auth/refresh', {
      refresh_token: refreshToken,
    });
    return data;
  },

  async logout(refreshToken?: string | null): Promise<{ status: string }> {
    const { data } = await apiClient.post<{ status: string }>('/auth/logout', {
      refresh_token: refreshToken || undefined,
    });
    return data;
  },

  async getMe(): Promise<UserProfile> {
    const { data } = await apiClient.get<UserProfile>('/auth/me');
    return data;
  },

  async listUsers(): Promise<UserProfile[]> {
    const { data } = await apiClient.get<UserProfile[]>('/auth/users');
    return data;
  },

  async createUser(payload: CreateUserPayload): Promise<UserProfile> {
    const { data } = await apiClient.post<UserProfile>('/auth/users', payload);
    return data;
  },
};
