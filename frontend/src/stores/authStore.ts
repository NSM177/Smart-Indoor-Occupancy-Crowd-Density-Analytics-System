import { create } from 'zustand';
import { UserProfile } from '../types';

const ACCESS_TOKEN_KEY = 'smart_occ_access_token';
const REFRESH_TOKEN_KEY = 'smart_occ_refresh_token';
const USER_PROFILE_KEY = 'smart_occ_user_profile';

function loadStoredUser(): UserProfile | null {
  try {
    const raw = localStorage.getItem(USER_PROFILE_KEY);
    return raw ? (JSON.parse(raw) as UserProfile) : null;
  } catch {
    return null;
  }
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: UserProfile | null;
  isAuthenticated: boolean;
  setSession: (
    accessToken: string,
    refreshToken: string,
    user: UserProfile,
  ) => void;
  updateUser: (user: UserProfile) => void;
  clearSession: () => void;
}

export const useAuthStore = create<AuthState>((set) => {
  const initialAccess =
    typeof window !== 'undefined'
      ? localStorage.getItem(ACCESS_TOKEN_KEY)
      : null;
  const initialRefresh =
    typeof window !== 'undefined'
      ? localStorage.getItem(REFRESH_TOKEN_KEY)
      : null;
  const initialUser =
    typeof window !== 'undefined' ? loadStoredUser() : null;

  return {
    accessToken: initialAccess,
    refreshToken: initialRefresh,
    user: initialUser,
    isAuthenticated: Boolean(initialAccess && initialUser),

    setSession: (accessToken, refreshToken, user) => {
      try {
        localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
        localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
        localStorage.setItem(USER_PROFILE_KEY, JSON.stringify(user));
      } catch {
        // Ignore storage errors in private mode
      }
      set({
        accessToken,
        refreshToken,
        user,
        isAuthenticated: true,
      });
    },

    updateUser: (user) => {
      try {
        localStorage.setItem(USER_PROFILE_KEY, JSON.stringify(user));
      } catch {
        // Ignore
      }
      set({ user });
    },

    clearSession: () => {
      try {
        localStorage.removeItem(ACCESS_TOKEN_KEY);
        localStorage.removeItem(REFRESH_TOKEN_KEY);
        localStorage.removeItem(USER_PROFILE_KEY);
      } catch {
        // Ignore
      }
      set({
        accessToken: null,
        refreshToken: null,
        user: null,
        isAuthenticated: false,
      });
    },
  };
});
