import React, { useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Eye,
  Search,
  ShieldCheck,
} from 'lucide-react';
import {
  EmptyState,
  LoadingState,
  ModalDialog,
  SectionCard,
  StatusBadge,
} from '../../components/ui/Primitives';
import {
  useAcknowledgeAlertMutation,
  useAlertsQuery,
  useResolveAlertMutation,
} from '../../hooks/useDomainQueries';
import { useUIStore } from '../../stores/uiStore';
import { AlertEntity } from '../../types';
import { formatDateTime, formatDensity } from '../../utils/formatters';

export const AlertManagementPage: React.FC = () => {
  const { selectedRoomId } = useUIStore();
  const [severityFilter, setSeverityFilter] = useState<string>('ALL');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedAlert, setSelectedAlert] = useState<AlertEntity | null>(null);

  const alertsQuery = useAlertsQuery({
    room_id: selectedRoomId,
    limit: 200,
  });
  const ackMutation = useAcknowledgeAlertMutation();
  const resolveMutation = useResolveAlertMutation();

  const filteredAlerts = useMemo(() => {
    const raw = alertsQuery.data || [];
    return raw.filter((item) => {
      if (severityFilter !== 'ALL' && item.severity !== severityFilter) {
        return false;
      }
      if (statusFilter === 'ACTIVE' && (item.is_acknowledged || item.is_resolved)) {
        return false;
      }
      if (
        statusFilter === 'ACKNOWLEDGED' &&
        (!item.is_acknowledged || item.is_resolved)
      ) {
        return false;
      }
      if (statusFilter === 'RESOLVED' && !item.is_resolved) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const hay = `${item.id} ${item.alert_type} ${item.message} ${item.room_id}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [alertsQuery.data, severityFilter, statusFilter, searchQuery]);

  if (alertsQuery.isLoading) {
    return <LoadingState label="Đang tải danh sách cảnh báo..." />;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">
            Alert Management (Quản Lý Cảnh Báo Mật Độ & Quá Tải)
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Theo dõi, lọc lịch sử, xem chi tiết và xác nhận xử lý (Acknowledge /
            Resolve) các cảnh báo phát sinh
          </p>
        </div>

        {/* Filter Controls */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Tìm theo ID, loại hoặc nội dung..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 pr-3 py-1.5 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-xs w-56"
            />
          </div>

          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="px-3 py-1.5 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-xs font-medium"
          >
            <option value="ALL">Mọi mức độ (All Severities)</option>
            <option value="WARNING">WARNING</option>
            <option value="CRITICAL">CRITICAL</option>
          </select>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-1.5 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-xs font-medium"
          >
            <option value="ALL">Mọi trạng thái (All Status)</option>
            <option value="ACTIVE">Chưa xác nhận (ACTIVE)</option>
            <option value="ACKNOWLEDGED">Đã xác nhận (ACKNOWLEDGED)</option>
            <option value="RESOLVED">Đã giải quyết (RESOLVED)</option>
          </select>
        </div>
      </div>

      {/* Alerts Table */}
      <SectionCard
        title={`Danh Sách Cảnh Báo (${filteredAlerts.length})`}
        subtitle="Hiển thị đầy đủ Alert ID, Room, Zone, Alert Type, Severity, Message, Timestamp và Status"
        icon={<AlertTriangle className="w-4 h-4" />}
      >
        {filteredAlerts.length === 0 ? (
          <EmptyState
            title="Không tìm thấy cảnh báo nào khớp bộ lọc"
            description="Thử thay đổi từ khóa tìm kiếm hoặc bộ lọc trạng thái."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400">
                  <th className="py-2.5 px-3">Alert ID</th>
                  <th className="py-2.5 px-3">Room / Zone</th>
                  <th className="py-2.5 px-3">Alert Type</th>
                  <th className="py-2.5 px-3">Severity</th>
                  <th className="py-2.5 px-3">Message</th>
                  <th className="py-2.5 px-3">Timestamp</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3 text-right">Thao tác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/70">
                {filteredAlerts.map((al) => {
                  const statusLabel = al.is_resolved
                    ? 'RESOLVED'
                    : al.is_acknowledged
                      ? 'ACKNOWLEDGED'
                      : 'ACTIVE';
                  return (
                    <tr key={al.id}>
                      <td className="py-2.5 px-3 font-mono text-slate-500">
                        {al.id.slice(0, 8)}...
                      </td>
                      <td className="py-2.5 px-3 font-mono">
                        <div>{al.room_id.slice(0, 8)}</div>
                        <div className="text-[10px] text-slate-400">
                          Zone: {al.zone_id ? al.zone_id.slice(0, 8) : 'All Room'}
                        </div>
                      </td>
                      <td className="py-2.5 px-3 font-mono font-semibold text-slate-700 dark:text-slate-300">
                        {al.alert_type}
                      </td>
                      <td className="py-2.5 px-3">
                        <StatusBadge status={al.severity} />
                      </td>
                      <td className="py-2.5 px-3 max-w-sm truncate text-slate-800 dark:text-slate-200">
                        {al.message}
                      </td>
                      <td className="py-2.5 px-3 font-mono text-slate-500 whitespace-nowrap">
                        {formatDateTime(al.triggered_at)}
                      </td>
                      <td className="py-2.5 px-3">
                        <StatusBadge status={statusLabel} />
                      </td>
                      <td className="py-2.5 px-3 text-right whitespace-nowrap space-x-1.5">
                        <button
                          type="button"
                          onClick={() => setSelectedAlert(al)}
                          className="px-2 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 font-medium inline-flex items-center gap-1"
                        >
                          <Eye className="w-3.5 h-3.5" />
                          Chi tiết
                        </button>
                        {!al.is_acknowledged && (
                          <button
                            type="button"
                            onClick={() => ackMutation.mutate(al.id)}
                            className="px-2.5 py-1 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-semibold inline-flex items-center gap-1"
                          >
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            Acknowledge
                          </button>
                        )}
                        {!al.is_resolved && (
                          <button
                            type="button"
                            onClick={() => resolveMutation.mutate(al.id)}
                            className="px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold inline-flex items-center gap-1"
                          >
                            <ShieldCheck className="w-3.5 h-3.5" />
                            Resolve
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      {/* Alert Details Modal */}
      <ModalDialog
        open={Boolean(selectedAlert)}
        onClose={() => setSelectedAlert(null)}
        title="Chi Tiết Cảnh Báo Hệ Thống"
      >
        {selectedAlert && (
          <div className="space-y-3 text-xs">
            <div className="flex items-center justify-between p-3 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800">
              <span className="font-mono text-slate-500">
                ID: {selectedAlert.id}
              </span>
              <StatusBadge status={selectedAlert.severity} size="md" />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800">
                <span className="text-slate-400 block">Loại cảnh báo</span>
                <span className="font-mono font-semibold mt-0.5 block">
                  {selectedAlert.alert_type}
                </span>
              </div>
              <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800">
                <span className="text-slate-400 block">Thời điểm phát sinh</span>
                <span className="font-mono font-semibold mt-0.5 block">
                  {formatDateTime(selectedAlert.triggered_at)}
                </span>
              </div>
              <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800">
                <span className="text-slate-400 block">Số người ghi nhận</span>
                <span className="font-mono font-bold text-base mt-0.5 block">
                  {selectedAlert.person_count} người
                </span>
              </div>
              <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800">
                <span className="text-slate-400 block">
                  Mật độ / Ngưỡng cấu hình
                </span>
                <span className="font-mono font-bold text-base mt-0.5 block">
                  {formatDensity(selectedAlert.density_value)} /{' '}
                  {selectedAlert.threshold_value}
                </span>
              </div>
            </div>

            <div className="p-3.5 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800">
              <span className="text-slate-400 block mb-1">
                Nội dung chi tiết
              </span>
              <p className="text-slate-900 dark:text-slate-100 font-medium">
                {selectedAlert.message}
              </p>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              {!selectedAlert.is_acknowledged && (
                <button
                  type="button"
                  onClick={async () => {
                    const updated = await ackMutation.mutateAsync(
                      selectedAlert.id,
                    );
                    setSelectedAlert(updated);
                  }}
                  className="px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-semibold"
                >
                  Acknowledge
                </button>
              )}
              <button
                type="button"
                onClick={() => setSelectedAlert(null)}
                className="px-4 py-2 rounded-lg bg-slate-100 dark:bg-slate-800 font-medium"
              >
                Đóng
              </button>
            </div>
          </div>
        )}
      </ModalDialog>
    </div>
  );
};
