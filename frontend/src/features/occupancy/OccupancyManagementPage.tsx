import React, { useState } from 'react';
import {
  ArrowDownLeft,
  ArrowUpRight,
  Download,
  History,
  TrendingUp,
  Users,
} from 'lucide-react';
import { OccupancyTrendChart } from '../../components/charts/RechartsWidgets';
import { StatCard } from '../../components/dashboard/StatCard';
import {
  EmptyState,
  LoadingState,
  SectionCard,
  StatusBadge,
} from '../../components/ui/Primitives';
import {
  useCurrentOccupancyQuery,
  useOccupancyHistoryQuery,
} from '../../hooks/useDomainQueries';
import { useLiveRoomMetrics } from '../../stores/realtimeStore';
import { useUIStore } from '../../stores/uiStore';
import {
  exportToCsv,
  formatDateTime,
  formatDensity,
  formatPercentage,
} from '../../utils/formatters';

export const OccupancyManagementPage: React.FC = () => {
  const selectedRoomId = useUIStore((s) => s.selectedRoomId);
  const liveRoom = useLiveRoomMetrics(selectedRoomId);
  const [sampleLimit, setSampleLimit] = useState<number>(100);

  const occQuery = useCurrentOccupancyQuery(selectedRoomId);
  const histQuery = useOccupancyHistoryQuery(selectedRoomId, {
    limit: sampleLimit,
  });

  if (occQuery.isLoading && !liveRoom) {
    return <LoadingState label="Đang tải dữ liệu quản lý lưu lượng người..." />;
  }

  const occ = occQuery.data;
  const records = histQuery.data || [];

  const currentCount = liveRoom?.current_count ?? occ?.current_count ?? 0;
  const inCount = liveRoom?.in_count ?? occ?.in_count ?? 0;
  const outCount = liveRoom?.out_count ?? occ?.out_count ?? 0;
  const maxCapacity = occ?.max_capacity ?? 60;
  const capRatio =
    liveRoom?.capacity_ratio ??
    occ?.capacity_ratio ??
    currentCount / Math.max(1, maxCapacity);
  const roomStatus = liveRoom?.room_status ?? occ?.room_status ?? 'NORMAL';

  const handleExportCsv = () => {
    exportToCsv(
      `occupancy_history_${selectedRoomId}.csv`,
      [
        'ID',
        'Room ID',
        'Recorded At',
        'Current Count',
        'In Count',
        'Out Count',
        'Overall Density (p/m2)',
        'Capacity Ratio (%)',
        'Room Status',
      ],
      records.map((r) => [
        r.id,
        r.room_id,
        r.recorded_at,
        r.total_count,
        r.in_count,
        r.out_count,
        r.overall_density,
        (r.capacity_ratio * 100).toFixed(1),
        r.room_status,
      ]),
    );
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">
            Occupancy Management (Quản Lý Lưu Lượng & Hiện Diện)
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Theo dõi người đi vào (IN), đi ra (OUT) qua Virtual Line và lịch sử
            hiện diện theo thời gian thực
          </p>
        </div>

        <div className="flex items-center gap-2">
          <select
            value={sampleLimit}
            onChange={(e) => setSampleLimit(Number(e.target.value))}
            className="px-3 py-1.5 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-xs font-medium"
          >
            <option value={50}>50 mẫu gần nhất</option>
            <option value={100}>100 mẫu gần nhất</option>
            <option value={250}>250 mẫu gần nhất</option>
            <option value={500}>500 mẫu gần nhất</option>
          </select>

          <button
            type="button"
            onClick={handleExportCsv}
            disabled={records.length === 0}
            className="px-3.5 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:opacity-40 text-white text-xs font-semibold flex items-center gap-1.5 transition"
          >
            <Download className="w-3.5 h-3.5" />
            Export CSV
          </button>
        </div>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Hiện diện trong phòng (Current Count)"
          value={`${currentCount} / ${maxCapacity}`}
          subValue={`Tỷ lệ lấp đầy: ${formatPercentage(capRatio, true)}`}
          icon={<Users className="w-5 h-5" />}
          accentColor="sky"
        />
        <StatCard
          label="Tổng lượt đi vào (Cumulative IN)"
          value={`+${inCount}`}
          subValue="Qua đường Virtual Line"
          icon={<ArrowDownLeft className="w-5 h-5" />}
          accentColor="emerald"
        />
        <StatCard
          label="Tổng lượt đi ra (Cumulative OUT)"
          value={`-${outCount}`}
          subValue="Qua đường Virtual Line"
          icon={<ArrowUpRight className="w-5 h-5" />}
          accentColor="amber"
        />
        <StatCard
          label="Trạng thái Sức chứa Phòng"
          value={roomStatus}
          subValue={`Còn trống: ${Math.max(0, maxCapacity - currentCount)} chỗ`}
          icon={<TrendingUp className="w-5 h-5" />}
          accentColor={
            roomStatus === 'CRITICAL'
              ? 'rose'
              : roomStatus === 'WARNING'
                ? 'amber'
                : 'emerald'
          }
        />
      </div>

      {/* Occupancy Chart */}
      <SectionCard
        title="Biểu Đồ Chuỗi Thời Gian Lưu Lượng Người (Occupancy Time-Series)"
        subtitle={`Hiển thị ${records.length} mẫu lịch sử gần nhất của phòng ${
          occ?.room_name || selectedRoomId
        }`}
        icon={<TrendingUp className="w-4 h-4" />}
      >
        {records.length === 0 ? (
          <EmptyState
            title="Chưa có bản ghi lịch sử"
            description="Các mẫu lưu lượng sẽ được lưu định kỳ vào bảng occupancy_records."
          />
        ) : (
          <OccupancyTrendChart records={records} maxCapacity={maxCapacity} />
        )}
      </SectionCard>

      {/* Historical Records Table */}
      <SectionCard
        title="Nhật Ký Bản Ghi Hiện Diện (Occupancy History Log)"
        subtitle="Dữ liệu chi tiết từ bảng occupancy_records trong PostgreSQL"
        icon={<History className="w-4 h-4" />}
      >
        {records.length === 0 ? (
          <EmptyState title="Chưa có bản ghi nào" />
        ) : (
          <div className="overflow-x-auto max-h-96">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                <tr>
                  <th className="py-2.5 px-3">ID</th>
                  <th className="py-2.5 px-3">Thời điểm ghi nhận</th>
                  <th className="py-2.5 px-3">Hiện diện (Total)</th>
                  <th className="py-2.5 px-3">Lượt vào (IN)</th>
                  <th className="py-2.5 px-3">Lượt ra (OUT)</th>
                  <th className="py-2.5 px-3">Mật độ (ng/m²)</th>
                  <th className="py-2.5 px-3">Lấp đầy (%)</th>
                  <th className="py-2.5 px-3">Trạng thái</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/70">
                {records.map((rec) => (
                  <tr key={rec.id}>
                    <td className="py-2 px-3 font-mono text-slate-400">
                      #{rec.id}
                    </td>
                    <td className="py-2 px-3 font-mono">
                      {formatDateTime(rec.recorded_at)}
                    </td>
                    <td className="py-2 px-3 font-bold font-mono text-slate-900 dark:text-slate-100">
                      {rec.total_count} người
                    </td>
                    <td className="py-2 px-3 font-mono text-emerald-600 dark:text-emerald-400">
                      +{rec.in_count}
                    </td>
                    <td className="py-2 px-3 font-mono text-amber-600 dark:text-amber-400">
                      -{rec.out_count}
                    </td>
                    <td className="py-2 px-3 font-mono">
                      {formatDensity(rec.overall_density)}
                    </td>
                    <td className="py-2 px-3 font-mono">
                      {formatPercentage(rec.capacity_ratio, true)}
                    </td>
                    <td className="py-2 px-3">
                      <StatusBadge status={rec.room_status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    </div>
  );
};
