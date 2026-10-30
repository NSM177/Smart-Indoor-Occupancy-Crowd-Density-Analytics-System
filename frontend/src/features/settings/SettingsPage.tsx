import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Check,
  Moon,
  Plus,
  Server,
  Shield,
  Sun,
  UserPlus,
  Users,
} from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { SectionCard } from '../../components/ui/Primitives';
import { AI_SERVICE_URL, API_BASE_URL, WS_URL } from '../../lib/axios';
import { authService } from '../../services/authService';
import { useAuthStore } from '../../stores/authStore';
import { useRealtimeStore } from '../../stores/realtimeStore';
import { useUIStore } from '../../stores/uiStore';
import { UserRole } from '../../types';
import { formatDateTime } from '../../utils/formatters';

export const SettingsPage: React.FC = () => {
  const { theme, setTheme } = useUIStore();
  const { user, isAuthenticated } = useAuthStore();
  const connectionStatus = useRealtimeStore((s) => s.connectionStatus);
  const qc = useQueryClient();

  const isAdmin = user?.role === 'ADMIN';

  const usersQuery = useQuery({
    queryKey: ['system-users'],
    queryFn: () => authService.listUsers(),
    enabled: Boolean(isAuthenticated && isAdmin),
  });

  const [newUsername, setNewUsername] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [newFullName, setNewFullName] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState<UserRole>('OPERATOR');
  const [userMsg, setUserMsg] = useState<string | null>(null);
  const [userErr, setUserErr] = useState<string | null>(null);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setUserMsg(null);
    setUserErr(null);
    try {
      await authService.createUser({
        username: newUsername.trim(),
        email: newEmail.trim(),
        full_name: newFullName.trim(),
        password: newPassword,
        role: newRole,
      });
      setUserMsg(`Đã tạo tài khoản '${newUsername}' (${newRole}) thành công.`);
      setNewUsername('');
      setNewEmail('');
      setNewFullName('');
      setNewPassword('');
      qc.invalidateQueries({ queryKey: ['system-users'] });
    } catch (err) {
      setUserErr(
        err instanceof Error ? err.message : 'Không thể tạo tài khoản mới.',
      );
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">
          Settings (Cấu Hình Hệ Thống & Quản Trị Tài Khoản)
        </h1>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
          Tùy chỉnh giao diện Sáng/Tối, kiểm tra kết nối dịch vụ và phân quyền
          người dùng RBAC (ADMIN / OPERATOR)
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Theme & Display Settings */}
        <SectionCard
          title="Giao Diện Hiển Thị (Theme & Visual Ergonomics)"
          subtitle="Tối ưu cho việc giám sát liên tục trong thời gian dài"
          icon={
            theme === 'dark' ? (
              <Moon className="w-4 h-4" />
            ) : (
              <Sun className="w-4 h-4" />
            )
          }
        >
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => setTheme('dark')}
              className={`p-4 rounded-xl border text-left transition ${
                theme === 'dark'
                  ? 'border-sky-500 bg-sky-500/10'
                  : 'border-slate-200 dark:border-slate-800'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-bold">Dark Mode (Control Room)</span>
                <Moon className="w-4 h-4 text-sky-400" />
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                Độ tương phản cao, giảm mỏi mắt khi giám sát 24/7.
              </p>
            </button>

            <button
              type="button"
              onClick={() => setTheme('light')}
              className={`p-4 rounded-xl border text-left transition ${
                theme === 'light'
                  ? 'border-sky-500 bg-sky-500/10'
                  : 'border-slate-200 dark:border-slate-800'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-bold">Light Mode (Office)</span>
                <Sun className="w-4 h-4 text-amber-500" />
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                Giao diện sáng thanh lịch cho môi trường văn phòng.
              </p>
            </button>
          </div>
        </SectionCard>

        {/* Endpoint Configuration */}
        <SectionCard
          title="Thông Số Kết Nối Dịch Vụ (Environment Endpoints)"
          subtitle="Đọc từ biến môi trường Vite (VITE_API_BASE_URL, VITE_WS_URL)"
          icon={<Server className="w-4 h-4" />}
        >
          <div className="space-y-2.5 text-xs">
            <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 flex items-center justify-between">
              <span className="text-slate-500">VITE_API_BASE_URL</span>
              <code className="font-mono text-sky-600 dark:text-sky-400">
                {API_BASE_URL}
              </code>
            </div>
            <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 flex items-center justify-between">
              <span className="text-slate-500">VITE_WS_URL</span>
              <code className="font-mono text-emerald-600 dark:text-emerald-400">
                {WS_URL} ({connectionStatus})
              </code>
            </div>
            <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 flex items-center justify-between">
              <span className="text-slate-500">VITE_AI_SERVICE_URL</span>
              <code className="font-mono text-violet-600 dark:text-violet-400">
                {AI_SERVICE_URL}
              </code>
            </div>
          </div>
        </SectionCard>
      </div>

      {/* Current User Profile & Admin RBAC Management */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <SectionCard
          title="Hồ Sơ Phiên Đăng Nhập (Current Session & RBAC)"
          subtitle="Xác thực bằng JWT Access Token & Refresh Token"
          icon={<Shield className="w-4 h-4" />}
        >
          {isAuthenticated && user ? (
            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800">
                  <span className="text-slate-400 block">Tên đăng nhập</span>
                  <span className="font-bold text-sm mt-0.5 block">
                    {user.username}
                  </span>
                </div>
                <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800">
                  <span className="text-slate-400 block">Vai trò (Role)</span>
                  <span className="font-mono font-bold text-sm text-sky-500 mt-0.5 block">
                    {user.role}
                  </span>
                </div>
                <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800">
                  <span className="text-slate-400 block">Họ tên</span>
                  <span className="font-medium mt-0.5 block">
                    {user.full_name || 'N/A'}
                  </span>
                </div>
                <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800">
                  <span className="text-slate-400 block">Email</span>
                  <span className="font-mono mt-0.5 block">{user.email}</span>
                </div>
              </div>
            </div>
          ) : (
            <div className="py-6 text-center space-y-3">
              <p className="text-xs text-slate-500">
                Bạn đang xem ở chế độ khách. Hãy đăng nhập tài khoản{' '}
                <strong>ADMIN</strong> hoặc <strong>OPERATOR</strong> để sử dụng
                đầy đủ chức năng quản trị.
              </p>
              <Link
                to="/login"
                className="inline-flex px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold"
              >
                Đi tới trang Đăng nhập
              </Link>
            </div>
          )}
        </SectionCard>

        {/* Admin Create User Form */}
        <SectionCard
          title="Tạo Tài Khoản Người Dùng Mới (Chỉ dành cho ADMIN)"
          subtitle="Phân quyền ADMIN (Toàn quyền) hoặc OPERATOR (Vận hành)"
          icon={<UserPlus className="w-4 h-4" />}
        >
          {!isAdmin ? (
            <div className="py-8 text-center text-xs text-slate-500">
              Vui lòng đăng nhập bằng tài khoản có vai trò{' '}
              <strong className="text-sky-500">ADMIN</strong> (mặc định:{' '}
              <code>admin / Admin@123</code>) để tạo và quản lý người dùng.
            </div>
          ) : (
            <form onSubmit={handleCreateUser} className="space-y-3 text-xs">
              {userMsg && (
                <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-500 flex items-center gap-1.5">
                  <Check className="w-4 h-4" />
                  {userMsg}
                </div>
              )}
              {userErr && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-500">
                  {userErr}
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-500 mb-1">Username</label>
                  <input
                    type="text"
                    required
                    value={newUsername}
                    onChange={(e) => setNewUsername(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800"
                  />
                </div>
                <div>
                  <label className="block text-slate-500 mb-1">Email</label>
                  <input
                    type="email"
                    required
                    value={newEmail}
                    onChange={(e) => setNewEmail(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800"
                  />
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-slate-500 mb-1">Họ và tên</label>
                  <input
                    type="text"
                    required
                    value={newFullName}
                    onChange={(e) => setNewFullName(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800"
                  />
                </div>
                <div>
                  <label className="block text-slate-500 mb-1">Mật khẩu</label>
                  <input
                    type="password"
                    required
                    minLength={6}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800"
                  />
                </div>
                <div>
                  <label className="block text-slate-500 mb-1">Vai trò</label>
                  <select
                    value={newRole}
                    onChange={(e) => setNewRole(e.target.value as UserRole)}
                    className="w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800"
                  >
                    <option value="OPERATOR">OPERATOR</option>
                    <option value="ADMIN">ADMIN</option>
                  </select>
                </div>
              </div>

              <button
                type="submit"
                className="px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-semibold inline-flex items-center gap-1.5"
              >
                <Plus className="w-4 h-4" />
                Tạo Tài Khoản
              </button>
            </form>
          )}
        </SectionCard>
      </div>

      {/* Admin Users Table */}
      {isAdmin && usersQuery.data && (
        <SectionCard
          title={`Danh Sách Tài Khoản Hệ Thống (${usersQuery.data.length})`}
          icon={<Users className="w-4 h-4" />}
        >
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-500">
                  <th className="py-2 px-3">Username</th>
                  <th className="py-2 px-3">Email</th>
                  <th className="py-2 px-3">Họ tên</th>
                  <th className="py-2 px-3">Vai trò</th>
                  <th className="py-2 px-3">Ngày tạo</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {usersQuery.data.map((u) => (
                  <tr key={u.id}>
                    <td className="py-2 px-3 font-bold">{u.username}</td>
                    <td className="py-2 px-3 font-mono">{u.email}</td>
                    <td className="py-2 px-3">{u.full_name}</td>
                    <td className="py-2 px-3 font-mono text-sky-500 font-semibold">
                      {u.role}
                    </td>
                    <td className="py-2 px-3 font-mono text-slate-400">
                      {formatDateTime(u.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}
    </div>
  );
};
