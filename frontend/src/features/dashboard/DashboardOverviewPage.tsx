import React from 'react';
import { Link } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  Building2,
  Camera,
  CheckCircle2,
  Clock,
  Cpu,
  Flame,
  TrendingUp,
  Users,
} from 'lucide-react';
import {
  DensityTrendChart,
  OccupancyTrendChart,
  PeakHoursBarChart,
} from '../../components/charts/RechartsWidgets';
import { StatCard } from '../../components/dashboard/StatCard';
import {
  EmptyState,
  ErrorState,
  LoadingState,
  SectionCard,
  StatusBadge,
} from '../../components/ui/Primitives';
import {
  useAcknowledgeAlertMutation,
  useAlertsQuery,
  useAnalyticsOverviewQuery,
  useCurrentDensityQuery,
  useCurrentOccupancyQuery,
  useDevicesQuery,
  useOccupancyHistoryQuery,
  usePeakHoursQuery,
} from '../../hooks/useDomainQueries';
import { useLiveRoomMetrics } from '../../stores/realtimeStore';
import { useUIStore } from '../../stores/uiStore';
import {
  formatDateTime,
  formatDensity,
  formatPercentage,
} from '../../utils/formatters';

export const DashboardOverviewPage: React.FC = () => {
  const selectedRoomId = useUIStore((s) => s.selectedRoomId);
  const liveRoom = useLiveRoomMetrics(selectedRoomId);

  const occQuery = useCurrentOccupancyQuery(selectedRoomId);
  const denQuery = useCurrentDensityQuery(selectedRoomId);
  const histQuery = useOccupancyHistoryQuery(selectedRoomId, { limit: 60 });
  const peakQuery = usePeakHoursQuery(selectedRoomId, 7);
  const overviewQuery = useAnalyticsOverviewQuery(selectedRoomId, 24);
  const alertsQuery = useAlertsQuery({ room_id: selectedRoomId, limit: 8 });
  const devicesQuery = useDevicesQuery(selectedRoomId);
  const ackMutation = useAcknowledgeAlertMutation();

  if (occQuery.isLoading && !liveRoom) {
    return <LoadingState label="Đang tải bảng điều khiển tổng quan..." />;
  }

  if (occQuery.isError && !liveRoom) {
    return (
      <ErrorState
        message={occQuery.error.message}
        onRetry={() => occQuery.refetch()}
      />
    );
  }

  const occ = occQuery.data;
  const den = denQuery.data;
  const devices = devicesQuery.data || [];
  const alerts = alertsQuery.data || [];
  const historyRecords = histQuery.data || [];
  const peakItems = peakQuery.data || [];

  const currentCount = liveRoom?.current_count ?? occ?.current_count ?? 0;
  const inCount = liveRoom?.in_count ?? occ?.in_count ?? 0;
  const outCount = liveRoom?.out_count ?? occ?.out_count ?? 0;
  const maxCapacity = occ?.max_capacity ?? den?.max_capacity ?? 60;
  const overallDensity =
    liveRoom?.overall_density ??
    occ?.overall_density ??
    den?.overall_density_per_sqm ??
    0;
  const capacityRatio =
    liveRoom?.capacity_ratio ??
    occ?.capacity_ratio ??
    currentCount / Math.max(1, maxCapacity);
  const roomStatus = liveRoom?.room_status ?? occ?.room_status ?? 'NORMAL';

  const activeAlertsCount = alerts.filter((a) => !a.is_resolved).length;
  const onlineDevicesCount = devices.filter((d) => d.is_online).length;
  const primaryDevice = devices[0];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">
            Dashboard Tổng Quan Giám Sát
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Phòng đang chọn:{' '}
            <strong className="text-slate-800 dark:text-slate-200">
              {occ?.room_name || selectedRoomId}
            </strong>{' '}
            • Diện tích: {den?.area_sqm ?? 120} m²
          </p>
        </div>

        <div className="flex items-center gap-2">
          <StatusBadge status={roomStatus} size="md" pulse />
          <Link
            to="/monitoring"
            className="px-3.5 py-2 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold flex items-center gap-1.5 transition"
          >
            Mở Live Monitoring
            <ArrowUpRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>

      {/* 5 Statistics KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard
          label="Total People (Hiện diện)"
          value={currentCount}
          subValue={`Vào: ${inCount} • Ra: ${outCount}`}
          icon={<Users className="w-5 h-5" />}
          accentColor="sky"
        />
        <StatCard
          label="Room Capacity (Sức chứa)"
          value={maxCapacity}
          subValue={`Diện tích: ${den?.area_sqm ?? 120} m²`}
          icon={<Building2 className="w-5 h-5" />}
          accentColor="emerald"
        />
        <StatCard
          label="Occupancy Rate (Tỷ lệ lấp đầy)"
          value={formatPercentage(capacityRatio, true)}
          subValue={`Mật độ: ${formatDensity(overallDensity)} người/m²`}
          icon={<Flame className="w-5 h-5" />}
          accentColor={
            roomStatus === 'CRITICAL'
              ? 'rose'
              : roomStatus === 'WARNING'
                ? 'amber'
                : 'emerald'
          }
        />
        <StatCard
          label="Active Alerts (Cảnh báo mở)"
          value={activeAlertsCount}
          subValue={`Tổng ghi nhận: ${alerts.length}`}
          icon={<AlertTriangle className="w-5 h-5" />}
          accentColor={activeAlertsCount > 0 ? 'rose' : 'emerald'}
        />
        <StatCard
          label="Connected Devices (Thiết bị)"
          value={`${onlineDevicesCount}/${devices.length || 1}`}
          subValue={
            primaryDevice
              ? `LED: ${primaryDevice.led_state} • Buzzer: ${
                  primaryDevice.buzzer_active ? 'ON' : 'OFF'
                }`
              : 'Raspberry Pi Node'
          }
          icon={<Cpu className="w-5 h-5" />}
          accentColor="violet"
        />
      </div>

      {/* Realtime Monitoring Status Strip */}
      <SectionCard
        title="Trạng Thái Hệ Thống Thời Gian Thực (Realtime Monitoring Status)"
        subtitle="Tổng hợp trạng thái Phòng, Mật độ, Camera AI và Node Raspberry Pi 4/5"
        icon={<Activity className="w-4 h-4" />}
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800">
            <span className="text-[11px] text-slate-500 dark:text-slate-400 block">
              Số người hiện tại
            </span>
            <div className="text-lg font-bold font-mono text-slate-900 dark:text-slate-100 mt-1">
              {currentCount} / {maxCapacity} người
            </div>
          </div>

          <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800">
            <span className="text-[11px] text-slate-500 dark:text-slate-400 block">
              Trạng thái phòng
            </span>
            <div className="mt-1.5">
              <StatusBadge status={roomStatus} pulse />
            </div>
          </div>

          <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800">
            <span className="text-[11px] text-slate-500 dark:text-slate-400 block">
              Mức mật độ & Vùng đông nhất
            </span>
            <div className="text-sm font-bold font-mono text-sky-600 dark:text-sky-400 mt-1">
              {formatDensity(overallDensity)} người/m²
              {den?.busiest_zone && (
                <span className="block text-[11px] font-sans font-normal text-slate-500 dark:text-slate-400">
                  Đông nhất: {den.busiest_zone.zone_code} (
                  {den.busiest_zone.person_count} người)
                </span>
              )}
            </div>
          </div>

          <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800">
            <span className="text-[11px] text-slate-500 dark:text-slate-400 flex items-center gap-1">
              <Camera className="w-3.5 h-3.5 text-sky-500" />
              Trạng thái Camera AI
            </span>
            <div className="text-xs font-semibold text-slate-900 dark:text-slate-100 mt-1.5 flex items-center justify-between">
              <span>
                {primaryDevice?.resolution_width ?? 1280}x
                {primaryDevice?.resolution_height ?? 720}
              </span>
              <span className="font-mono text-emerald-500">
                {occ?.inference_fps
                  ? `${occ.inference_fps.toFixed(1)} FPS`
                  : `${primaryDevice?.fps_target ?? 15} FPS`}
              </span>
            </div>
          </div>

          <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800">
            <span className="text-[11px] text-slate-500 dark:text-slate-400 flex items-center gap-1">
              <Cpu className="w-3.5 h-3.5 text-violet-500" />
              Raspberry Pi Edge
            </span>
            <div className="mt-1.5 flex items-center justify-between">
              <StatusBadge
                status={primaryDevice?.is_online ? 'ONLINE' : 'OFFLINE'}
              />
              <span className="text-xs font-mono text-slate-600 dark:text-slate-300">
                LED: {primaryDevice?.led_state || 'GREEN'}
              </span>
            </div>
          </div>
        </div>
      </SectionCard>

      {/* Row 1 Charts: Occupancy Trend & Density Trend */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <SectionCard
          title="Occupancy Trend (Biến thiên số người theo thời gian)"
          subtitle="Chuỗi thời gian thực tế ghi nhận từ AI Computer Vision"
          icon={<TrendingUp className="w-4 h-4" />}
        >
          {historyRecords.length === 0 ? (
            <EmptyState
              title="Chưa có dữ liệu chuỗi thời gian"
              description="Dữ liệu sẽ tự động hiển thị khi AI Service gửi telemetry qua MQTT."
            />
          ) : (
            <OccupancyTrendChart
              records={historyRecords}
              maxCapacity={maxCapacity}
            />
          )}
        </SectionCard>

        <SectionCard
          title="Density Trend (Biến thiên mật độ người/m²)"
          subtitle="So sánh mật độ thực tế với ngưỡng cảnh báo của phòng"
          icon={<Flame className="w-4 h-4" />}
        >
          {historyRecords.length === 0 ? (
            <EmptyState
              title="Chưa có mẫu lịch sử mật độ"
              description="Hệ thống đang chờ bản ghi mật độ từ luồng AI."
            />
          ) : (
            <DensityTrendChart
              records={historyRecords}
              criticalDensity={0.8}
            />
          )}
        </SectionCard>
      </div>

      {/* Row 2: Peak-Hour Statistics & Recent Alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <SectionCard
          title="Hourly Occupancy & Peak-Hour Statistics"
          subtitle={`Phân bố lưu lượng trung bình & cực đại theo khung giờ (24h • TB: ${
            overviewQuery.data?.average_occupancy ?? 0
          } người)`}
          icon={<Clock className="w-4 h-4" />}
        >
          {peakItems.length === 0 ? (
            <EmptyState
              title="Chưa có thống kê giờ cao điểm"
              description="Cần ít nhất một bản ghi trong cơ sở dữ liệu để tổng hợp theo khung giờ."
            />
          ) : (
            <PeakHoursBarChart items={peakItems} />
          )}
        </SectionCard>

        <SectionCard
          title="Recent Alerts (Cảnh Báo Gần Đây)"
          subtitle="Danh sách cảnh báo mật độ & quá tải mới nhất"
          icon={<AlertTriangle className="w-4 h-4" />}
          action={
            <Link
              to="/alerts"
              className="text-xs font-semibold text-sky-600 dark:text-sky-400 hover:underline"
            >
              Xem tất cả
            </Link>
          }
        >
          {alerts.length === 0 ? (
            <EmptyState
              title="Không có cảnh báo nào"
              description="Không gian phòng đang hoạt động trong ngưỡng mật độ an toàn."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400">
                    <th className="py-2 pr-3">Mức độ</th>
                    <th className="py-2 pr-3">Nội dung cảnh báo</th>
                    <th className="py-2 pr-3">Thời điểm</th>
                    <th className="py-2 text-right">Trạng thái</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800/70">
                  {alerts.slice(0, 6).map((alert) => (
                    <tr key={alert.id}>
                      <td className="py-2.5 pr-3">
                        <StatusBadge status={alert.severity} />
                      </td>
                      <td className="py-2.5 pr-3 font-medium text-slate-800 dark:text-slate-200 max-w-xs truncate">
                        {alert.message}
                      </td>
                      <td className="py-2.5 pr-3 font-mono text-slate-500 dark:text-slate-400 whitespace-nowrap">
                        {formatDateTime(alert.triggered_at)}
                      </td>
                      <td className="py-2.5 text-right whitespace-nowrap">
                        {alert.is_resolved ? (
                          <span className="text-emerald-500 font-semibold">
                            Đã xử lý
                          </span>
                        ) : alert.is_acknowledged ? (
                          <span className="text-sky-500 font-semibold">
                            Đã xác nhận
                          </span>
                        ) : (
                          <button
                            type="button"
                            onClick={() => ackMutation.mutate(alert.id)}
                            className="px-2.5 py-1 rounded-lg bg-sky-600/10 hover:bg-sky-600/20 text-sky-600 dark:text-sky-400 font-semibold inline-flex items-center gap-1 transition"
                          >
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            Acknowledge
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>
      </div>
    </div>
  );
};
