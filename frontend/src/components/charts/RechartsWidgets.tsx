import React from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  ForecastPoint,
  OccupancyRecord,
  PeakHourItem,
  ZoneDensitySnapshot,
} from '../../types';
import { formatTimeShort } from '../../utils/formatters';

// ============================================================================
// 1. Occupancy Trend Area Chart
// ============================================================================
export const OccupancyTrendChart: React.FC<{
  records: OccupancyRecord[];
  maxCapacity: number;
}> = ({ records, maxCapacity }) => {
  const data = records
    .slice()
    .reverse()
    .map((r) => ({
      time: formatTimeShort(r.recorded_at),
      total: r.total_count,
      inCount: r.in_count,
      outCount: r.out_count,
    }));

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
          <defs>
            <linearGradient id="occFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#0284c7" stopOpacity={0.35} />
              <stop offset="95%" stopColor="#0284c7" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.15)" />
          <XAxis dataKey="time" tick={{ fontSize: 11, fill: '#94a3b8' }} />
          <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} />
          <Tooltip
            contentStyle={{
              backgroundColor: '#0f172a',
              borderColor: '#1e293b',
              borderRadius: '0.5rem',
              fontSize: '12px',
              color: '#f8fafc',
            }}
          />
          <Legend wrapperStyle={{ fontSize: '12px' }} />
          {maxCapacity > 0 && (
            <ReferenceLine
              y={maxCapacity}
              stroke="#f43f5e"
              strokeDasharray="4 4"
              label={{
                value: `Max (${maxCapacity})`,
                fill: '#f43f5e',
                fontSize: 11,
              }}
            />
          )}
          <Area
            type="monotone"
            dataKey="total"
            name="Hiện diện (Người)"
            stroke="#0ea5e9"
            strokeWidth={2}
            fill="url(#occFill)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
};

// ============================================================================
// 2. Density Trend Line Chart
// ============================================================================
export const DensityTrendChart: React.FC<{
  records: OccupancyRecord[];
  criticalDensity: number;
}> = ({ records, criticalDensity }) => {
  const data = records
    .slice()
    .reverse()
    .map((r) => ({
      time: formatTimeShort(r.recorded_at),
      density: Number(r.overall_density.toFixed(3)),
      ratioPct: Number((r.capacity_ratio * 100).toFixed(1)),
    }));

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.15)" />
          <XAxis dataKey="time" tick={{ fontSize: 11, fill: '#94a3b8' }} />
          <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} />
          <Tooltip
            contentStyle={{
              backgroundColor: '#0f172a',
              borderColor: '#1e293b',
              borderRadius: '0.5rem',
              fontSize: '12px',
              color: '#f8fafc',
            }}
          />
          <Legend wrapperStyle={{ fontSize: '12px' }} />
          {criticalDensity > 0 && (
            <ReferenceLine
              y={criticalDensity}
              stroke="#f59e0b"
              strokeDasharray="4 4"
              label={{
                value: `Ngưỡng (${criticalDensity} ng/m²)`,
                fill: '#f59e0b',
                fontSize: 11,
              }}
            />
          )}
          <Line
            type="monotone"
            dataKey="density"
            name="Mật độ (người/m²)"
            stroke="#10b981"
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};

// ============================================================================
// 3. Peak Hours Bar Chart
// ============================================================================
export const PeakHoursBarChart: React.FC<{
  items: PeakHourItem[];
}> = ({ items }) => {
  const data = items.map((item) => ({
    hour: `${String(item.hour_of_day).padStart(2, '0')}:00`,
    avgCount: item.avg_count,
    maxCount: item.max_count,
  }));

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.15)" />
          <XAxis dataKey="hour" tick={{ fontSize: 11, fill: '#94a3b8' }} />
          <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} />
          <Tooltip
            contentStyle={{
              backgroundColor: '#0f172a',
              borderColor: '#1e293b',
              borderRadius: '0.5rem',
              fontSize: '12px',
              color: '#f8fafc',
            }}
          />
          <Legend wrapperStyle={{ fontSize: '12px' }} />
          <Bar
            dataKey="avgCount"
            name="Trung bình (người)"
            fill="#0ea5e9"
            radius={[4, 4, 0, 0]}
          />
          <Bar
            dataKey="maxCount"
            name="Cao điểm (người)"
            fill="#f59e0b"
            radius={[4, 4, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};

// ============================================================================
// 4. Zone Comparison Bar Chart
// ============================================================================
export const ZoneComparisonBarChart: React.FC<{
  zones: ZoneDensitySnapshot[];
}> = ({ zones }) => {
  const data = zones.map((z) => ({
    code: z.zone_code,
    name: z.zone_name,
    personCount: z.person_count,
    maxCapacity: z.max_capacity,
    density: Number(z.density_per_sqm.toFixed(2)),
  }));

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.15)" />
          <XAxis dataKey="code" tick={{ fontSize: 11, fill: '#94a3b8' }} />
          <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} />
          <Tooltip
            contentStyle={{
              backgroundColor: '#0f172a',
              borderColor: '#1e293b',
              borderRadius: '0.5rem',
              fontSize: '12px',
              color: '#f8fafc',
            }}
          />
          <Legend wrapperStyle={{ fontSize: '12px' }} />
          <Bar
            dataKey="personCount"
            name="Số người hiện tại"
            fill="#0284c7"
            radius={[4, 4, 0, 0]}
          />
          <Bar
            dataKey="maxCapacity"
            name="Sức chứa vùng"
            fill="#334155"
            radius={[4, 4, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};

// ============================================================================
// 5. OLS Short-Term Forecast Composed Chart
// ============================================================================
export const ForecastConfidenceChart: React.FC<{
  predictions: ForecastPoint[];
}> = ({ predictions }) => {
  const data = predictions.map((p) => ({
    offset: `+${p.minute_offset}m`,
    predicted: p.predicted_count,
    low: p.confidence_low,
    high: p.confidence_high,
  }));

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart
          data={data}
          margin={{ top: 8, right: 12, left: -12, bottom: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.15)" />
          <XAxis dataKey="offset" tick={{ fontSize: 11, fill: '#94a3b8' }} />
          <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} />
          <Tooltip
            contentStyle={{
              backgroundColor: '#0f172a',
              borderColor: '#1e293b',
              borderRadius: '0.5rem',
              fontSize: '12px',
              color: '#f8fafc',
            }}
          />
          <Legend wrapperStyle={{ fontSize: '12px' }} />
          <Area
            type="monotone"
            dataKey="high"
            name="Cận trên (95% CI)"
            stroke="none"
            fill="#38bdf8"
            fillOpacity={0.14}
          />
          <Line
            type="monotone"
            dataKey="predicted"
            name="Dự báo OLS (Người)"
            stroke="#0ea5e9"
            strokeWidth={2.5}
          />
          <Line
            type="monotone"
            dataKey="low"
            name="Cận dưới (95% CI)"
            stroke="#64748b"
            strokeDasharray="3 3"
            strokeWidth={1.5}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
};
