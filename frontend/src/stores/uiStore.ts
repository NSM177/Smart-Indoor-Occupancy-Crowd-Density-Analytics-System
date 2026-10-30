import { create } from 'zustand';

export type ThemeMode = 'dark' | 'light';

const THEME_STORAGE_KEY = 'smart_occ_theme';
const ROOM_STORAGE_KEY = 'smart_occ_selected_room';

function applyDomTheme(theme: ThemeMode): void {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  if (theme === 'dark') {
    root.classList.add('dark');
  } else {
    root.classList.remove('dark');
  }
}

interface UIState {
  theme: ThemeMode;
  sidebarCollapsed: boolean;
  mobileSidebarOpen: boolean;
  notificationDrawerOpen: boolean;
  selectedRoomId: string;
  setTheme: (theme: ThemeMode) => void;
  toggleTheme: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setMobileSidebarOpen: (open: boolean) => void;
  setNotificationDrawerOpen: (open: boolean) => void;
  setSelectedRoomId: (roomId: string) => void;
}

export const useUIStore = create<UIState>((set, get) => {
  const savedTheme =
    (typeof window !== 'undefined' &&
      (localStorage.getItem(THEME_STORAGE_KEY) as ThemeMode | null)) ||
    'dark';
  applyDomTheme(savedTheme);

  const savedRoom =
    (typeof window !== 'undefined' &&
      localStorage.getItem(ROOM_STORAGE_KEY)) ||
    'room1';

  return {
    theme: savedTheme,
    sidebarCollapsed: false,
    mobileSidebarOpen: false,
    notificationDrawerOpen: false,
    selectedRoomId: savedRoom,

    setTheme: (theme) => {
      try {
        localStorage.setItem(THEME_STORAGE_KEY, theme);
      } catch {
        // Ignore
      }
      applyDomTheme(theme);
      set({ theme });
    },

    toggleTheme: () => {
      const next: ThemeMode = get().theme === 'dark' ? 'light' : 'dark';
      get().setTheme(next);
    },

    setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
    setMobileSidebarOpen: (open) => set({ mobileSidebarOpen: open }),
    setNotificationDrawerOpen: (open) =>
      set({ notificationDrawerOpen: open }),

    setSelectedRoomId: (roomId) => {
      try {
        localStorage.setItem(ROOM_STORAGE_KEY, roomId);
      } catch {
        // Ignore
      }
      set({ selectedRoomId: roomId });
    },
  };
});
