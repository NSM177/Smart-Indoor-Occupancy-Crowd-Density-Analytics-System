import React from 'react';
import {
  AlertCircle,
  Inbox,
  Loader2,
  RefreshCw,
  X,
} from 'lucide-react';
import { DeviceStatusType, SeverityLevel } from '../../types';

// ============================================================================
// StatusBadge
// ============================================================================
interface StatusBadgeProps {
  status: SeverityLevel | DeviceStatusType | string;
  size?: 'sm' | 'md';
  pulse?: boolean;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  size = 'sm',
  pulse = false,
}) => {
  const normalized = String(status || 'NORMAL').toUpperCase();
  let classes =
    'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30';
  let dotColor = 'bg-emerald-500';

  if (normalized === 'CRITICAL' || normalized === 'OVERCROWDED') {
    classes =
      'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/30';
    dotColor = 'bg-rose-500';
  } else if (normalized === 'WARNING' || normalized === 'HIGH') {
    classes =
      'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30';
    dotColor = 'bg-amber-500';
  } else if (normalized === 'OFFLINE' || normalized === 'DISCONNECTED') {
    classes =
      'bg-slate-500/10 text-slate-600 dark:text-slate-400 border-slate-500/30';
    dotColor = 'bg-slate-400';
  } else if (normalized === 'ACKNOWLEDGED') {
    classes =
      'bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/30';
    dotColor = 'bg-sky-500';
  }

  const sizeCls =
    size === 'md'
      ? 'px-3 py-1 text-xs font-semibold'
      : 'px-2.5 py-0.5 text-[11px] font-semibold';

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border ${sizeCls} ${classes}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${dotColor} ${
          pulse || normalized === 'CRITICAL' ? 'animate-pulse' : ''
        }`}
      />
      {normalized}
    </span>
  );
};

// ============================================================================
// SectionCard
// ============================================================================
interface SectionCardProps {
  title: string;
  subtitle?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export const SectionCard: React.FC<SectionCardProps> = ({
  title,
  subtitle,
  icon,
  action,
  children,
  className = '',
}) => (
  <div
    className={`bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-sm overflow-hidden ${className}`}
  >
    <div className="px-5 py-4 border-b border-slate-100 dark:border-slate-800/80 flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2.5">
        {icon && (
          <div className="p-2 rounded-lg bg-slate-100 dark:bg-slate-800 text-sky-600 dark:text-sky-400">
            {icon}
          </div>
        )}
        <div>
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            {title}
          </h3>
          {subtitle && (
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              {subtitle}
            </p>
          )}
        </div>
      </div>
      {action && <div className="flex items-center gap-2">{action}</div>}
    </div>
    <div className="p-5">{children}</div>
  </div>
);

// ============================================================================
// LoadingState, EmptyState, ErrorState
// ============================================================================
export const LoadingState: React.FC<{ label?: string }> = ({
  label = 'Đang tải dữ liệu hệ thống...',
}) => (
  <div className="py-12 flex flex-col items-center justify-center gap-3 text-slate-500 dark:text-slate-400">
    <Loader2 className="w-7 h-7 animate-spin text-sky-500" />
    <span className="text-xs font-medium">{label}</span>
  </div>
);

export const EmptyState: React.FC<{
  title: string;
  description?: string;
  action?: React.ReactNode;
}> = ({ title, description, action }) => (
  <div className="py-10 px-4 text-center flex flex-col items-center justify-center">
    <div className="w-11 h-11 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-slate-400 mb-3">
      <Inbox className="w-5 h-5" />
    </div>
    <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">
      {title}
    </p>
    {description && (
      <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 max-w-md">
        {description}
      </p>
    )}
    {action && <div className="mt-4">{action}</div>}
  </div>
);

export const ErrorState: React.FC<{
  message: string;
  onRetry?: () => void;
}> = ({ message, onRetry }) => (
  <div className="p-5 rounded-xl bg-rose-500/10 border border-rose-500/30 flex flex-wrap items-center justify-between gap-4">
    <div className="flex items-center gap-3">
      <AlertCircle className="w-5 h-5 text-rose-500 shrink-0" />
      <div>
        <h4 className="text-sm font-semibold text-rose-600 dark:text-rose-300">
          Không thể tải dữ liệu
        </h4>
        <p className="text-xs text-rose-600/80 dark:text-rose-300/80 mt-0.5">
          {message}
        </p>
      </div>
    </div>
    {onRetry && (
      <button
        type="button"
        onClick={onRetry}
        className="px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-xs font-medium flex items-center gap-1.5 transition"
      >
        <RefreshCw className="w-3.5 h-3.5" />
        Thử lại
      </button>
    )}
  </div>
);

// ============================================================================
// ModalDialog & SideDrawer
// ============================================================================
interface ModalDialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  maxWidthClass?: string;
}

export const ModalDialog: React.FC<ModalDialogProps> = ({
  open,
  onClose,
  title,
  children,
  maxWidthClass = 'max-w-lg',
}) => {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-xs">
      <div
        className={`w-full ${maxWidthClass} bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-2xl overflow-hidden`}
      >
        <div className="px-5 py-3.5 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            {title}
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-5 max-h-[80vh] overflow-y-auto">{children}</div>
      </div>
    </div>
  );
};

interface SideDrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}

export const SideDrawer: React.FC<SideDrawerProps> = ({
  open,
  onClose,
  title,
  children,
}) => {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/60 backdrop-blur-xs">
      <div className="w-full max-w-md bg-white dark:bg-slate-900 border-l border-slate-200 dark:border-slate-800 h-full flex flex-col shadow-2xl">
        <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            {title}
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  );
};
