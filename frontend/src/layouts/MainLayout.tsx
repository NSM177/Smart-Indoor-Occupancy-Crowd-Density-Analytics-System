import React from 'react';
import {
  Link,
  NavLink,
  Outlet,
  useLocation,
  useNavigate,
} from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bell,
  Building2,
  ChevronLeft,
  ChevronRight,
  Cpu,
  Flame,
  LayoutDashboard,
  LogIn,
  LogOut,
  Menu,
  Moon,
  Settings,
  Shield,
  Sun,
  Users,
  Video,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { SideDrawer, StatusBadge } from '../components/ui/Primitives';
import { useRoomsQuery } from '../hooks/useDomainQueries';
import { useRealtimeWebSocket } from '../hooks/useRealtimeWebSocket';
import { authService } from '../services/authService';
import { useAuthStore } from '../stores/authStore';
import { useRealtimeStore } from '../stores/realtimeStore';
import { useUIStore } from '../stores/uiStore';
import { formatDateTime } from '../utils/formatters';

interface NavItem {
  label: string;
  path: string;
  icon: React.ReactNode;
}

export const SIDEBAR_NAV_ITEMS: NavItem[] = [
  {
    label: 'Dashboard',
    path: '/dashboard',
    icon: <LayoutDashboard className="w-4 h-4" />,
  },
  {
    label: 'Live Monitoring',
    path: '/monitoring',
    icon: <Video className="w-4 h-4" />,
  },
  {
    label: 'Occupancy Management',
    path: '/occupancy',
    icon: <Users className="w-4 h-4" />,
  },
  {
    label: 'Density Analysis',
    path: '/density',
    icon: <Flame className="w-4 h-4" />,
  },
  {
    label: 'Room & Zone Management',
    path: '/rooms',
    icon: <Building2 className="w-4 h-4" />,
  },
  {
    label: 'Analytics & Reports',
    path: '/analytics',
    icon: <BarChart3 className="w-4 h-4" />,
  },
  {
    label: 'Alert Management',
    path: '/alerts',
    icon: <AlertTriangle className="w-4 h-4" />,
  },
  {
    label: 'Device Management',
    path: '/devices',
    icon: <Cpu className="w-4 h-4" />,
  },
  {
    label: 'Settings',
    path: '/settings',
    icon: <Settings className="w-4 h-4" />,
  },
];

export const MainLayout: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();

  const {
    theme,
    toggleTheme,
    sidebarCollapsed,
    setSidebarCollapsed,
    mobileSidebarOpen,
    setMobileSidebarOpen,
    notificationDrawerOpen,
    setNotificationDrawerOpen,
    selectedRoomId,
    setSelectedRoomId,
  } = useUIStore();

  const { user, isAuthenticated, refreshToken, clearSession } = useAuthStore();
  const markAlertsRead = useRealtimeStore((s) => s.markAlertsRead);

  const {
    connectionStatus,
    isStale,
    liveAlerts,
    unreadAlertCount,
  } = useRealtimeWebSocket();

  const { data: rooms = [] } = useRoomsQuery();

  const activeNavItem =
    SIDEBAR_NAV_ITEMS.find((item) => location.pathname.startsWith(item.path)) ||
    SIDEBAR_NAV_ITEMS[0];

  const handleLogout = async () => {
    try {
      await authService.logout(refreshToken);
    } catch {
      // Ignore network error on logout
    } finally {
      clearSession();
      navigate('/login');
    }
  };

  return (
    <div className="min-h-screen flex bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100">
      {/* Desktop Sidebar */}
      <aside
        className={`hidden lg:flex flex-col border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 transition-all duration-200 shrink-0 ${
          sidebarCollapsed ? 'w-20' : 'w-64'
        }`}
      >
        <div className="h-16 px-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <Link to="/dashboard" className="flex items-center gap-2.5 overflow-hidden">
            <div className="w-9 h-9 rounded-xl bg-sky-600 text-white flex items-center justify-center shrink-0 shadow-xs">
              <Activity className="w-5 h-5" />
            </div>
            {!sidebarCollapsed && (
              <div className="truncate">
                <span className="text-sm font-bold tracking-tight block leading-tight">
                  SmartOccupancy
                </span>
                <span className="text-[11px] text-slate-500 dark:text-slate-400 block">
                  AI & IoT Analytics
                </span>
              </div>
            )}
          </Link>

          <button
            type="button"
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
            title={sidebarCollapsed ? 'Mở rộng Sidebar' : 'Thu gọn Sidebar'}
          >
            {sidebarCollapsed ? (
              <ChevronRight className="w-4 h-4" />
            ) : (
              <ChevronLeft className="w-4 h-4" />
            )}
          </button>
        </div>

        <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
          {SIDEBAR_NAV_ITEMS.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              title={item.label}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-medium transition ${
                  isActive
                    ? 'bg-sky-600 text-white shadow-xs'
                    : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800/80 hover:text-slate-900 dark:hover:text-slate-100'
                }`
              }
            >
              <span className="shrink-0">{item.icon}</span>
              {!sidebarCollapsed && <span className="truncate">{item.label}</span>}
            </NavLink>
          ))}
        </nav>

        {/* Footer System Info */}
        <div className="p-3 border-t border-slate-200 dark:border-slate-800 text-[11px] text-slate-500 dark:text-slate-400">
          {!sidebarCollapsed ? (
            <div className="flex items-center justify-between">
              <span>FastAPI + YOLOv8 + RPi</span>
              <span className="font-mono text-emerald-500">v2.0</span>
            </div>
          ) : (
            <div className="text-center font-mono text-emerald-500">v2.0</div>
          )}
        </div>
      </aside>

      {/* Mobile Sidebar Overlay */}
      {mobileSidebarOpen && (
        <div className="fixed inset-0 z-50 lg:hidden flex">
          <div
            className="fixed inset-0 bg-slate-950/60"
            onClick={() => setMobileSidebarOpen(false)}
          />
          <aside className="relative z-10 w-64 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 flex flex-col">
            <div className="h-16 px-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
              <span className="font-bold text-sm">SmartOccupancy</span>
              <button
                type="button"
                onClick={() => setMobileSidebarOpen(false)}
                className="text-xs text-slate-400"
              >
                Đóng
              </button>
            </div>
            <nav className="flex-1 p-3 space-y-1">
              {SIDEBAR_NAV_ITEMS.map((item) => (
                <NavLink
                  key={item.path}
                  to={item.path}
                  onClick={() => setMobileSidebarOpen(false)}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-medium ${
                      isActive
                        ? 'bg-sky-600 text-white'
                        : 'text-slate-600 dark:text-slate-400'
                    }`
                  }
                >
                  {item.icon}
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </nav>
          </aside>
        </div>
      )}

      {/* Main Content Column */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Header */}
        <header className="h-16 px-4 lg:px-6 border-b border-slate-200 dark:border-slate-800 bg-white/90 dark:bg-slate-900/90 backdrop-blur-md sticky top-0 z-30 flex items-center justify-between gap-3">
          {/* Left: Mobile Menu + Breadcrumb */}
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              onClick={() => setMobileSidebarOpen(true)}
              className="lg:hidden p-2 rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              <Menu className="w-5 h-5" />
            </button>

            <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-xs">
              <span className="text-slate-400 hidden sm:inline">Smart Building</span>
              <span className="text-slate-400 hidden sm:inline">/</span>
              <span className="font-semibold text-slate-900 dark:text-slate-100 truncate">
                {activeNavItem.label}
              </span>
            </nav>
          </div>

          {/* Right: Room Selector, WS Status, Theme, Notifications, User Profile */}
          <div className="flex items-center gap-2.5">
            {/* Active Room Selector */}
            <div className="hidden md:flex items-center gap-1.5 bg-slate-100 dark:bg-slate-800/90 border border-slate-200 dark:border-slate-700/80 rounded-lg px-2.5 py-1.5">
              <Building2 className="w-3.5 h-3.5 text-sky-500" />
              <select
                aria-label="Chọn phòng giám sát"
                value={selectedRoomId}
                onChange={(e) => setSelectedRoomId(e.target.value)}
                className="bg-transparent text-xs font-medium text-slate-800 dark:text-slate-200 focus:outline-none"
              >
                {rooms.length === 0 && <option value="room1">room1 — Phòng chính</option>}
                {rooms.map((r) => (
                  <option
                    key={r.id}
                    value={r.code}
                    className="bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100"
                  >
                    {r.code} — {r.name}
                  </option>
                ))}
              </select>
            </div>

            {/* WebSocket Connection & Stale Indicator */}
            <div
              className={`px-2.5 py-1 rounded-full border text-[11px] font-medium flex items-center gap-1.5 ${
                connectionStatus === 'CONNECTED'
                  ? isStale
                    ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30'
                    : 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30'
                  : 'bg-slate-500/10 text-slate-500 dark:text-slate-400 border-slate-500/30'
              }`}
              title={
                isStale
                  ? 'Kết nối WebSocket mở nhưng chưa có gói tin mới trong 30 giây qua'
                  : `WebSocket: ${connectionStatus}`
              }
            >
              {connectionStatus === 'CONNECTED' ? (
                <Wifi className="w-3.5 h-3.5" />
              ) : (
                <WifiOff className="w-3.5 h-3.5" />
              )}
              <span className="hidden sm:inline">
                {connectionStatus === 'CONNECTED'
                  ? isStale
                    ? 'WS Idle'
                    : 'Realtime'
                  : connectionStatus}
              </span>
            </div>

            {/* Light / Dark Mode Toggle */}
            <button
              type="button"
              onClick={toggleTheme}
              className="p-2 rounded-lg border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
              title={
                theme === 'dark'
                  ? 'Chuyển sang Giao diện Sáng (Light Mode)'
                  : 'Chuyển sang Giao diện Tối (Dark Mode)'
              }
            >
              {theme === 'dark' ? (
                <Sun className="w-4 h-4 text-amber-400" />
              ) : (
                <Moon className="w-4 h-4 text-slate-700" />
              )}
            </button>

            {/* Notification Center Button */}
            <button
              type="button"
              onClick={() => {
                markAlertsRead();
                setNotificationDrawerOpen(true);
              }}
              className="relative p-2 rounded-lg border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
              title="Trung tâm thông báo cảnh báo"
            >
              <Bell className="w-4 h-4" />
              {unreadAlertCount > 0 && (
                <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-rose-500 text-white text-[10px] font-bold flex items-center justify-center">
                  {unreadAlertCount > 9 ? '9+' : unreadAlertCount}
                </span>
              )}
            </button>

            {/* User Profile / Auth Controls */}
            {isAuthenticated && user ? (
              <div className="flex items-center gap-2 pl-2 border-l border-slate-200 dark:border-slate-800">
                <div className="hidden sm:block text-right">
                  <div className="text-xs font-semibold text-slate-900 dark:text-slate-100 leading-tight">
                    {user.username}
                  </div>
                  <div className="text-[10px] font-mono text-sky-600 dark:text-sky-400 flex items-center justify-end gap-0.5">
                    <Shield className="w-2.5 h-2.5" />
                    {user.role}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={handleLogout}
                  className="p-2 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-rose-500/10 hover:text-rose-500 text-slate-600 dark:text-slate-300 transition"
                  title="Đăng xuất"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <Link
                to="/login"
                className="px-3 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold flex items-center gap-1.5 transition"
              >
                <LogIn className="w-3.5 h-3.5" />
                <span>Đăng nhập</span>
              </Link>
            )}
          </div>
        </header>

        {/* Page Main Content */}
        <main className="flex-1 p-4 lg:p-6 max-w-[1600px] w-full mx-auto">
          <Outlet />
        </main>
      </div>

      {/* Notification Center Drawer */}
      <SideDrawer
        open={notificationDrawerOpen}
        onClose={() => setNotificationDrawerOpen(false)}
        title="Trung Tâm Thông Báo Cảnh Báo (Realtime Alerts)"
      >
        <div className="space-y-3">
          {liveAlerts.length === 0 ? (
            <p className="text-xs text-slate-500 dark:text-slate-400 text-center py-8">
              Chưa có cảnh báo mới phát sinh trong phiên làm việc hiện tại.
            </p>
          ) : (
            liveAlerts.map((al) => (
              <div
                key={al.id}
                className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 space-y-1.5"
              >
                <div className="flex items-center justify-between">
                  <StatusBadge status={al.severity} pulse />
                  <span className="text-[11px] font-mono text-slate-400">
                    {formatDateTime(al.triggered_at)}
                  </span>
                </div>
                <p className="text-xs font-medium text-slate-800 dark:text-slate-200">
                  {al.message}
                </p>
              </div>
            ))
          )}

          <div className="pt-3 border-t border-slate-200 dark:border-slate-800">
            <Link
              to="/alerts"
              onClick={() => setNotificationDrawerOpen(false)}
              className="block w-full py-2 text-center rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold"
            >
              Xem toàn bộ Lịch sử Cảnh báo
            </Link>
          </div>
        </div>
      </SideDrawer>
    </div>
  );
};
