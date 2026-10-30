import React, { useMemo, useState } from 'react';
import {
  AlertTriangle,
  BarChart3,
  Calendar,
  Clock,
  Download,
  Flame,
  TrendingUp,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  DensityTrendChart,
  ForecastConfidenceChart,
  OccupancyTrendChart,
  PeakHoursBarChart,
  ZoneComparisonBarChart,
} from '../../components/charts/RechartsWidgets';
import { StatCard } from '../../components/dashboard/StatCard';
import {
  EmptyState,
  LoadingState,
  SectionCard,
} from '../../components/ui/Primitives';
import {
  useAlertsQuery,
  useAnalyticsOverviewQuery,
  useCurrentDensityQuery,
  useForecastQuery,
  useOccupancyHistoryQuery,
  useOccupancySeriesQuery,
  usePeakHoursQuery,
  useRoomZonesQuery,
} from '../../hooks/useDomainQueries';
import { useUIStore } from '../../stores/uiStore';
import {
  exportToCsv,
  formatDensity,
  formatPercentage,
} from '../../utils/formatters';

export const AnalyticsReportsPage: React.FC = () => {
  const { selectedRoomId } = useUIStore();
  const [periodHours, setPeriodHours] = useState<number>(24);
  const [granularity, setGranularity] = useState<'hourly' | 'daily'>('hourly');
  const [selectedZoneId, setSelectedZoneId] = useState<string>('ALL');
  const [forecastHorizon, setForecastHorizon] = useState<number>(30);

  const overviewQuery = useAnalyticsOverviewQuery(selectedRoomId, periodHours);
  const peakQuery = usePeakHoursQuery(
    selectedRoomId,
    Math.max(1, Math.round(periodHours / 24)),
  );
  const occSeriesQuery = useOccupancySeriesQuery({
    room_id: selectedRoomId,
    granularity,
    hours: periodHours,
    days: Math.max(1, Math.round(periodHours / 24)),
  });
  const histQuery = useOccupancyHistoryQuery(selectedRoomId, { limit: 120 });
  const denCurrentQuery = useCurrentDensityQuery(selectedRoomId);
  const zonesQuery = useRoomZonesQuery(selectedRoomId);
  const forecastQuery = useForecastQuery(selectedRoomId, forecastHorizon);
  const alertsQuery = useAlertsQuery({ room_id: selectedRoomId, limit: 200 });

  // Group Alert Frequency by Alert Type / Severity
  const alertFrequencyData = useMemo(() => {
    const list = alertsQuery.data || [];
    const grouped: Record<
      string,
      { type: string; WARNING: number; CRITICAL: number }
    > = {};
    list.forEach((a) => {
      const key = a.alert_type || 'THRESHOLD';
      if (!grouped[key]) {
        grouped[key] = { type: key, WARNING: 0, CRITICAL: 0 };
      }
      if (a.severity === 'CRITICAL') {
        grouped[key].CRITICAL += 1;
      } else {
        grouped[key].WARNING += 1;
      }
    });
    return Object.values(grouped);
  }, [alertsQuery.data]);

  if (overviewQuery.isLoading) {
    return <LoadingState label="Đang tổng hợp báo cáo phân tích lịch sử..." />;
  }

  const ov = overviewQuery.data;
  const rawRecords = histQuery.data || [];
  const bucketSeries = occSeriesQuery.data?.series || [];
  const zonesList = zonesQuery.data || [];
  const filteredZoneMetrics = (denCurrentQuery.data?.zones || []).filter(
    (z) => selectedZoneId === 'ALL' || z.zone_id === selectedZoneId,
  );

  const handleExportReportCsv = () => {
    exportToCsv(
      `analytics_report_${selectedRoomId}_${granularity}.csv`,
      [
        'Bucket',
        'Avg Occupancy',
        'Peak Occupancy',
        'Avg Density (p/m2)',
        'Peak Density (p/m2)',
      ],
      bucketSeries.map((b) => [
        b.hour_bucket || b.date_bucket || b.recorded_at,
        b.avg_occupancy ?? b.total_count ?? 0,
        b.peak_occupancy ?? b.total_count ?? 0,
        b.avg_density ?? b.overall_density ?? 0,
        b.peak_density ?? b.overall_density ?? 0,
      ]),
    );
  };

  return (
    <div className="space-y-6">
      {/* Page Header & Filters */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">
            Analytics & Reports (Thống Kê Lịch Sử, Giờ Cao Điểm & Dự Báo)
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Phân tích chuyên sâu theo giờ/ngày, so sánh với kỳ trước và dự báo
            xu hướng đám đông tương lai gần
          </p>
        </div>

        {/* Filter Bar */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg px-2.5 py-1.5">
            <Calendar className="w-3.5 h-3.5 text-sky-500" />
            <select
              value={periodHours}
              onChange={(e) => setPeriodHours(Number(e.target.value))}
              className="bg-transparent text-xs font-medium focus:outline-none"
            >
              <option value={12}>12 giờ qua</option>
              <option value={24}>24 giờ qua (1 ngày)</option>
              <option value={72}>72 giờ qua (3 ngày)</option>
              <option value={168}>7 ngày qua</option>
            </select>
          </div>

          <select
            value={granularity}
            onChange={(e) =>
              setGranularity(e.target.value as 'hourly' | 'daily')
            }
            className="px-3 py-1.5 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-xs font-medium"
          >
            <option value="hourly">Tổng hợp theo Giờ (Hourly)</option>
            <option value="daily">Tổng hợp theo Ngày (Daily)</option>
          </select>

          <select
            value={selectedZoneId}
            onChange={(e) => setSelectedZoneId(e.target.value)}
            className="px-3 py-1.5 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-xs font-medium"
          >
            <option value="ALL">Tất cả Khu vực (All Zones)</option>
            {zonesList.map((z) => (
              <option key={z.id} value={z.id}>
                {z.code} — {z.name}
              </option>
            ))}
          </select>

          <button
            type="button"
            onClick={handleExportReportCsv}
            className="px-3.5 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold flex items-center gap-1.5 transition"
          >
            <Download className="w-3.5 h-3.5" />
            Export CSV
          </button>
        </div>
      </div>

      {/* Overview KPI Cards with Period Comparison */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Average Occupancy (Số người TB)"
          value={ov?.average_occupancy ?? 0}
          subValue={`Đỉnh: ${ov?.peak_occupancy ?? 0} người (${ov?.total_samples ?? 0} mẫu)`}
          trendLabel={
            ov?.period_comparison
              ? `${
                  ov.period_comparison.occupancy_change_pct >= 0 ? '+' : ''
                }${ov.period_comparison.occupancy_change_pct}% vs kỳ trước`
              : undefined
          }
          icon={<BarChart3 className="w-5 h-5" />}
          accentColor="sky"
        />
        <StatCard
          label="Average Density (Mật độ TB)"
          value={`${formatDensity(ov?.average_density_per_sqm ?? 0)} ng/m²`}
          subValue={`Đỉnh: ${formatDensity(ov?.peak_density_per_sqm ?? 0)} ng/m²`}
          trendLabel={
            ov?.period_comparison
              ? `${
                  ov.period_comparison.density_change_pct >= 0 ? '+' : ''
                }${ov.period_comparison.density_change_pct}% vs kỳ trước`
              : undefined
          }
          icon={<Flame className="w-5 h-5" />}
          accentColor="emerald"
        />
        <StatCard
          label="Time Over Threshold (Thời gian vượt ngưỡng)"
          value={`${ov?.time_over_threshold_minutes ?? 0} phút`}
          subValue={`Tỷ lệ vượt ngưỡng: ${formatPercentage(
            ov?.over_threshold_ratio_pct ?? 0,
          )}`}
          icon={<Clock className="w-5 h-5" />}
          accentColor="amber"
        />
        <StatCard
          label="Dự báo Xu hướng Ngắn hạn (OLS Trend)"
          value={forecastQuery.data?.trend || 'STABLE'}
          subValue={`Slope: ${forecastQuery.data?.slope_per_minute ?? 0}/phút • R²=${
            forecastQuery.data?.r_squared ?? 0
          }`}
          icon={<TrendingUp className="w-5 h-5" />}
          accentColor="violet"
        />
      </div>

      {/* Row 1: Occupancy Over Time & Density Over Time */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <SectionCard
          title="1. Occupancy Over Time (Số Người Theo Thời Gian)"
          subtitle="Biến thiên hiện diện thực tế so với sức chứa tối đa"
          icon={<TrendingUp className="w-4 h-4" />}
        >
          {rawRecords.length === 0 ? (
            <EmptyState title="Chưa có dữ liệu chuỗi thời gian" />
          ) : (
            <OccupancyTrendChart
              records={rawRecords}
              maxCapacity={denCurrentQuery.data?.max_capacity ?? 60}
            />
          )}
        </SectionCard>

        <SectionCard
          title="2. Density Over Time (Mật Độ Người/m² Theo Thời Gian)"
          subtitle="Chuỗi thời gian mật độ không gian kín"
          icon={<Flame className="w-4 h-4" />}
        >
          {rawRecords.length === 0 ? (
            <EmptyState title="Chưa có dữ liệu mật độ" />
          ) : (
            <DensityTrendChart records={rawRecords} criticalDensity={0.8} />
          )}
        </SectionCard>
      </div>

      {/* Row 2: Hourly/Daily Aggregated Occupancy & Peak Hours */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <SectionCard
          title={`3. ${
            granularity === 'daily' ? 'Daily Occupancy' : 'Hourly Occupancy'
          } (Tổng Hợp Theo ${granularity === 'daily' ? 'Ngày' : 'Giờ'})`}
          subtitle="So sánh lưu lượng trung bình và đỉnh điểm trong mỗi khung"
          icon={<BarChart3 className="w-4 h-4" />}
        >
          {bucketSeries.length === 0 ? (
            <EmptyState title="Chưa có dữ liệu tổng hợp" />
          ) : (
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={bucketSeries}>
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="rgba(148,163,184,0.15)"
                  />
                  <XAxis
                    dataKey={
                      granularity === 'daily' ? 'date_bucket' : 'hour_bucket'
                    }
                    tick={{ fontSize: 10, fill: '#94a3b8' }}
                  />
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
                    dataKey="avg_occupancy"
                    name="TB (người)"
                    fill="#0ea5e9"
                    radius={[4, 4, 0, 0]}
                  />
                  <Bar
                    dataKey="peak_occupancy"
                    name="Cao nhất (người)"
                    fill="#6366f1"
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </SectionCard>

        <SectionCard
          title="4. Peak Hours Distribution (Phân Tích Giờ Cao Điểm 00:00 – 23:00)"
          subtitle="Xác định khung giờ có lưu lượng tập trung đông nhất"
          icon={<Clock className="w-4 h-4" />}
        >
          {(peakQuery.data || []).length === 0 ? (
            <EmptyState title="Chưa có dữ liệu giờ cao điểm" />
          ) : (
            <PeakHoursBarChart items={peakQuery.data || []} />
          )}
        </SectionCard>
      </div>

      {/* Row 3: Zone Comparison, Short-Term Forecast & Alert Frequency */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <SectionCard
          title="5. Zone Comparison (So Sánh Khu Vực)"
          subtitle="Tương quan số người và sức chứa giữa các Zone"
          icon={<BarChart3 className="w-4 h-4" />}
        >
          <ZoneComparisonBarChart zones={filteredZoneMetrics} />
        </SectionCard>

        <SectionCard
          title="6. Dự Đoán Xu Hướng Tương Lai Gần (OLS Forecast)"
          subtitle="Dự báo số người kèm khoảng tin cậy 95%"
          icon={<TrendingUp className="w-4 h-4" />}
          action={
            <select
              value={forecastHorizon}
              onChange={(e) => setForecastHorizon(Number(e.target.value))}
              className="px-2 py-1 rounded bg-slate-100 dark:bg-slate-800 text-xs"
            >
              <option value={15}>+15 phút</option>
              <option value={30}>+30 phút</option>
              <option value={60}>+60 phút</option>
            </select>
          }
        >
          <ForecastConfidenceChart
            predictions={forecastQuery.data?.predictions || []}
          />
        </SectionCard>

        <SectionCard
          title="7. Alert Frequency (Tần Suất Cảnh Báo)"
          subtitle="Phân bố cảnh báo theo loại và mức độ nghiêm trọng"
          icon={<AlertTriangle className="w-4 h-4" />}
        >
          {alertFrequencyData.length === 0 ? (
            <EmptyState title="Chưa phát sinh cảnh báo" />
          ) : (
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={alertFrequencyData}>
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="rgba(148,163,184,0.15)"
                  />
                  <XAxis
                    dataKey="type"
                    tick={{ fontSize: 10, fill: '#94a3b8' }}
                  />
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
                    dataKey="WARNING"
                    name="WARNING"
                    fill="#f59e0b"
                    radius={[4, 4, 0, 0]}
                  />
                  <Bar
                    dataKey="CRITICAL"
                    name="CRITICAL"
                    fill="#f43f5e"
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </SectionCard>
      </div>
    </div>
  );
};
