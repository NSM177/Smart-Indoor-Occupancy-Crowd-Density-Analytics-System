import React from 'react';

interface StatCardProps {
  label: string;
  value: string | number;
  subValue?: string;
  icon: React.ReactNode;
  accentColor?: 'sky' | 'emerald' | 'amber' | 'rose' | 'violet';
  trendLabel?: string;
  trendPositive?: boolean;
}

const ACCENT_MAP: Record<
  NonNullable<StatCardProps['accentColor']>,
  string
> = {
  sky: 'bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/20',
  emerald:
    'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
  amber:
    'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20',
  rose: 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20',
  violet:
    'bg-violet-500/10 text-violet-600 dark:text-violet-400 border-violet-500/20',
};

export const StatCard: React.FC<StatCardProps> = ({
  label,
  value,
  subValue,
  icon,
  accentColor = 'sky',
  trendLabel,
}) => (
  <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-xs flex flex-col justify-between">
    <div className="flex items-start justify-between gap-2">
      <div>
        <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
          {label}
        </span>
        <div className="text-2xl font-bold text-slate-900 dark:text-slate-100 mt-1 font-mono tracking-tight">
          {value}
        </div>
      </div>
      <div
        className={`p-2.5 rounded-xl border ${ACCENT_MAP[accentColor]} shrink-0`}
      >
        {icon}
      </div>
    </div>

    {(subValue || trendLabel) && (
      <div className="mt-3 pt-2.5 border-t border-slate-100 dark:border-slate-800/80 flex items-center justify-between text-xs">
        {subValue && (
          <span className="text-slate-500 dark:text-slate-400 truncate">
            {subValue}
          </span>
        )}
        {trendLabel && (
          <span className="font-mono font-medium text-sky-600 dark:text-sky-400">
            {trendLabel}
          </span>
        )}
      </div>
    )}
  </div>
);
