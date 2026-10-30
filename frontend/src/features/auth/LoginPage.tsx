import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Activity, Lock, LogIn, User } from 'lucide-react';
import { authService } from '../../services/authService';
import { useAuthStore } from '../../stores/authStore';

export const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const setSession = useAuthStore((s) => s.setSession);

  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('Admin@123');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setLoading(true);
    try {
      const res = await authService.login({
        username: username.trim(),
        password,
      });
      setSession(res.access_token, res.refresh_token, res.user);
      navigate('/dashboard');
    } catch (err) {
      setErrorMsg(
        err instanceof Error
          ? err.message
          : 'Đăng nhập thất bại. Vui lòng kiểm tra tài khoản.',
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100">
      <div className="w-full max-w-md bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-xl space-y-6">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-xl bg-sky-600 text-white flex items-center justify-center shadow-xs">
            <Activity className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-base font-bold">
              Smart Indoor Occupancy System
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              AI Computer Vision & IoT Crowd Density Analytics
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {errorMsg && (
            <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-xs text-rose-500">
              {errorMsg}
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">
              Tên đăng nhập (Username)
            </label>
            <div className="relative">
              <User className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full pl-9 pr-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">
              Mật khẩu (Password)
            </label>
            <div className="relative">
              <Lock className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full pl-9 pr-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm"
              />
            </div>
          </div>

          <div className="flex items-center justify-between gap-2 text-[11px] text-slate-500">
            <button
              type="button"
              onClick={() => {
                setUsername('admin');
                setPassword('Admin@123');
              }}
              className="hover:text-sky-500 underline"
            >
              Điền nhanh Admin (admin / Admin@123)
            </button>
            <button
              type="button"
              onClick={() => {
                setUsername('operator');
                setPassword('Operator@123');
              }}
              className="hover:text-sky-500 underline"
            >
              Điền nhanh Operator
            </button>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 px-4 rounded-xl bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white text-sm font-semibold flex items-center justify-center gap-2 transition"
          >
            <LogIn className="w-4 h-4" />
            {loading ? 'Đang xác thực JWT...' : 'Đăng nhập Hệ thống'}
          </button>
        </form>
      </div>
    </div>
  );
};
