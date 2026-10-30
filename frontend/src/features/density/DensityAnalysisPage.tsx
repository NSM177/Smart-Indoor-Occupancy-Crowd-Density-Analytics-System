import React, { useState } from 'react';
import {
  Flame,
  Layers,
  Maximize2,
  Sliders,
  Sparkles,
  Users,
} from 'lucide-react';
import { ZoneComparisonBarChart } from '../../components/charts/RechartsWidgets';
import { InteractiveFloorPlan } from '../../components/monitoring/SpatialWidgets';
import {
  LoadingState,
  ModalDialog,
  SectionCard,
  StatusBadge,
} from '../../components/ui/Primitives';
import {
  useAiEngineRealtimeQuery,
  useCurrentDensityQuery,
  useRoomDetailQuery,
  useUpdateZoneMutation,
} from '../../hooks/useDomainQueries';
import { useRealtimeStore } from '../../stores/realtimeStore';
import { useUIStore } from '../../stores/uiStore';
import { ZoneEntity } from '../../types';
import { formatDensity, formatPercentage } from '../../utils/formatters';

export const DensityAnalysisPage: React.FC = () => {
  const selectedRoomId = useUIStore((s) => s.selectedRoomId);
  const liveRoom = useRealtimeStore((s) => s.liveRooms[selectedRoomId]);

  const roomQuery = useRoomDetailQuery(selectedRoomId);
  const denQuery = useCurrentDensityQuery(selectedRoomId);
  const aiDirectQuery = useAiEngineRealtimeQuery(true);
  const updateZoneMutation = useUpdateZoneMutation();

  const [editingZone, setEditingZone] = useState<ZoneEntity | null>(null);
  const [warnVal, setWarnVal] = useState<number>(0.5);
  const [critVal, setCritVal] = useState<number>(0.8);
  const [capVal, setCapVal] = useState<number>(15);
  const [modalError, setModalError] = useState<string | null>(null);

  if (roomQuery.isLoading || denQuery.isLoading) {
    return <LoadingState label="Đang tải bản đồ phân tích mật độ không gian..." />;
  }

  const room = roomQuery.data;
  const den = denQuery.data;
  const zones = room?.zones || [];
  const zoneMetrics = den?.zones || [];
  const busiest = den?.busiest_zone || null;
  const heatmapGrid =
    liveRoom?.heatmap_grid || aiDirectQuery.data?.heatmap_grid;

  const openThresholdEditor = (z: ZoneEntity) => {
    setEditingZone(z);
    setWarnVal(z.warning_density);
    setCritVal(z.critical_density);
    setCapVal(z.max_capacity);
    setModalError(null);
  };

  const handleSaveThresholds = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingZone) return;
    if (warnVal >= critVal) {
      setModalError('Ngưỡng WARNING phải nhỏ hơn ngưỡng CRITICAL.');
      return;
    }
    try {
      await updateZoneMutation.mutateAsync({
        zoneId: editingZone.id,
        payload: {
          warning_density: Number(warnVal),
          critical_density: Number(critVal),
          max_capacity: Number(capVal),
        },
      });
      setEditingZone(null);
    } catch (err) {
      setModalError(
        err instanceof Error ? err.message : 'Lỗi khi cập nhật ngưỡng vùng.',
      );
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">
            Density Analysis & Spatial Heatmap (Phân Tích Mật Độ Không Gian)
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Đánh giá mật độ người/m² trên từng Polygon Zone, hiển thị Gaussian
            Heatmap và xác định khu vực đông người nhất
          </p>
        </div>
        <StatusBadge status={den?.room_status || 'NORMAL'} size="md" pulse />
      </div>

      {/* Summary Banner: Overall Density & Busiest Zone Highlight */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <div>
            <span className="text-xs text-slate-500 dark:text-slate-400">
              Mật độ toàn phòng (Overall Density)
            </span>
            <div className="text-2xl font-bold font-mono text-slate-900 dark:text-slate-100 mt-1">
              {formatDensity(den?.overall_density_per_sqm ?? 0)}{' '}
              <span className="text-xs font-normal text-slate-400">
                người/m²
              </span>
            </div>
            <span className="text-xs text-slate-500 dark:text-slate-400 mt-1 block">
              Tổng diện tích hiệu chuẩn: {den?.area_sqm ?? 120} m²
            </span>
          </div>
          <div className="p-3 rounded-xl bg-sky-500/10 text-sky-500">
            <Maximize2 className="w-6 h-6" />
          </div>
        </div>

        <div className="p-5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <div>
            <span className="text-xs text-slate-500 dark:text-slate-400">
              Công suất sử dụng không gian (Utilization)
            </span>
            <div className="text-2xl font-bold font-mono text-slate-900 dark:text-slate-100 mt-1">
              {formatPercentage(den?.capacity_utilization_pct ?? 0)}
            </div>
            <span className="text-xs text-slate-500 dark:text-slate-400 mt-1 block">
              Hiện diện: {den?.total_count ?? 0} / {den?.max_capacity ?? 60}{' '}
              người
            </span>
          </div>
          <div className="p-3 rounded-xl bg-emerald-500/10 text-emerald-500">
            <Users className="w-6 h-6" />
          </div>
        </div>

        <div className="p-5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <div>
            <span className="text-xs text-amber-600 dark:text-amber-400 font-semibold flex items-center gap-1">
              <Sparkles className="w-3.5 h-3.5" />
              Khu vực đông người nhất (Busiest Zone)
            </span>
            {busiest ? (
              <>
                <div className="text-lg font-bold text-slate-900 dark:text-slate-100 mt-1">
                  {busiest.zone_name} ({busiest.zone_code})
                </div>
                <span className="text-xs font-mono text-sky-600 dark:text-sky-400 mt-0.5 block">
                  {busiest.person_count} người •{' '}
                  {formatDensity(busiest.density_per_sqm)} ng/m² (
                  {busiest.severity})
                </span>
              </>
            ) : (
              <div className="text-sm text-slate-400 mt-2">
                Chưa có dữ liệu vùng
              </div>
            )}
          </div>
          <div className="p-3 rounded-xl bg-amber-500/10 text-amber-500">
            <Flame className="w-6 h-6" />
          </div>
        </div>
      </div>

      {/* Interactive Spatial Floor Plan + Heatmap */}
      <InteractiveFloorPlan
        zones={zones}
        zoneMetrics={zoneMetrics}
        heatmapGrid={heatmapGrid}
        showSampleBlueprint
      />

      {/* Zone Density Breakdown Cards + Comparison Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <SectionCard
            title="Bảng Phân Tích Mật Độ Từng Khu Vực (Per-Zone Crowd Density)"
            subtitle="Cho phép Quản trị viên hiệu chỉnh ngưỡng mật độ cảnh báo trực tiếp"
            icon={<Layers className="w-4 h-4" />}
          >
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {zoneMetrics.map((zm) => {
                const zEntity = zones.find((z) => z.code === zm.zone_code);
                return (
                  <div
                    key={zm.zone_id}
                    className="p-4 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 flex flex-col justify-between gap-3"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                          {zm.zone_name}
                        </h4>
                        <span className="text-xs font-mono text-slate-500 dark:text-slate-400">
                          {zm.zone_code} • Diện tích: {zm.area_sqm} m²
                        </span>
                      </div>
                      <StatusBadge status={zm.severity} />
                    </div>

                    <div className="grid grid-cols-3 gap-2 text-xs">
                      <div className="p-2.5 rounded-lg bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800">
                        <span className="text-[10px] text-slate-400 block">
                          Số người
                        </span>
                        <span className="text-base font-bold font-mono">
                          {zm.person_count}/{zm.max_capacity}
                        </span>
                      </div>
                      <div className="p-2.5 rounded-lg bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800">
                        <span className="text-[10px] text-slate-400 block">
                          Mật độ
                        </span>
                        <span className="text-base font-bold font-mono text-sky-600 dark:text-sky-400">
                          {formatDensity(zm.density_per_sqm)}
                        </span>
                      </div>
                      <div className="p-2.5 rounded-lg bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800">
                        <span className="text-[10px] text-slate-400 block">
                          Sử dụng
                        </span>
                        <span className="text-base font-bold font-mono">
                          {formatPercentage(zm.utilization_pct)}
                        </span>
                      </div>
                    </div>

                    {zEntity && (
                      <div className="pt-2 border-t border-slate-200/70 dark:border-slate-800 flex items-center justify-between text-xs">
                        <span className="text-slate-500 dark:text-slate-400 font-mono">
                          Ngưỡng: {zEntity.warning_density}/
                          {zEntity.critical_density} ng/m²
                        </span>
                        <button
                          type="button"
                          onClick={() => openThresholdEditor(zEntity)}
                          className="px-2.5 py-1 rounded-lg bg-slate-200/70 dark:bg-slate-800 hover:bg-sky-600 hover:text-white text-xs font-medium flex items-center gap-1 transition"
                        >
                          <Sliders className="w-3 h-3" />
                          Cấu hình ngưỡng
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </SectionCard>
        </div>

        <SectionCard
          title="So Sánh Sức Chứa & Hiện Diện Giữa Các Vùng"
          subtitle="Tương quan phân bố đám đông"
          icon={<Flame className="w-4 h-4" />}
        >
          <ZoneComparisonBarChart zones={zoneMetrics} />
        </SectionCard>
      </div>

      {/* Modal Configure Zone Thresholds */}
      <ModalDialog
        open={Boolean(editingZone)}
        onClose={() => setEditingZone(null)}
        title={`Cấu hình Ngưỡng Mật Độ — ${editingZone?.name || ''}`}
      >
        <form onSubmit={handleSaveThresholds} className="space-y-4">
          {modalError && (
            <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-xs text-rose-500">
              {modalError}
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">
              Sức chứa tối đa của vùng (người)
            </label>
            <input
              type="number"
              min="1"
              value={capVal}
              onChange={(e) => setCapVal(Number(e.target.value))}
              className="w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">
                Ngưỡng WARNING (người/m²)
              </label>
              <input
                type="number"
                step="0.05"
                min="0.05"
                value={warnVal}
                onChange={(e) => setWarnVal(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">
                Ngưỡng CRITICAL (người/m²)
              </label>
              <input
                type="number"
                step="0.05"
                min="0.1"
                value={critVal}
                onChange={(e) => setCritVal(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm"
              />
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setEditingZone(null)}
              className="px-4 py-2 rounded-lg bg-slate-100 dark:bg-slate-800 text-xs font-medium"
            >
              Hủy
            </button>
            <button
              type="submit"
              className="px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold"
            >
              Lưu thay đổi
            </button>
          </div>
        </form>
      </ModalDialog>
    </div>
  );
};
