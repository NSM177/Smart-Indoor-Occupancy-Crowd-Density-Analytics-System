import React from 'react';
import {
  Activity,
  ArrowDownLeft,
  ArrowUpRight,
  Cpu,
  Gauge,
  Layers,
  Users,
  Video,
} from 'lucide-react';
import { LiveCameraFeed } from '../../components/monitoring/SpatialWidgets';
import {
  LoadingState,
  SectionCard,
  StatusBadge,
} from '../../components/ui/Primitives';
import {
  useAiEngineRealtimeQuery,
  useCurrentDensityQuery,
  useCurrentOccupancyQuery,
  useRoomDetailQuery,
} from '../../hooks/useDomainQueries';
import { useRealtimeStore } from '../../stores/realtimeStore';
import { useUIStore } from '../../stores/uiStore';
import { formatDensity, formatPercentage } from '../../utils/formatters';

export const LiveMonitoringPage: React.FC = () => {
  const selectedRoomId = useUIStore((s) => s.selectedRoomId);
  const liveRoom = useRealtimeStore((s) => s.liveRooms[selectedRoomId]);

  const roomQuery = useRoomDetailQuery(selectedRoomId);
  const occQuery = useCurrentOccupancyQuery(selectedRoomId);
  const denQuery = useCurrentDensityQuery(selectedRoomId);
  const aiDirectQuery = useAiEngineRealtimeQuery(true);

  if (roomQuery.isLoading && occQuery.isLoading) {
    return <LoadingState label="Đang kết nối luồng giám sát trực tiếp..." />;
  }

  const room = roomQuery.data;
  const occ = occQuery.data;
  const den = denQuery.data;
  const aiDirect = aiDirectQuery.data;

  const currentCount =
    liveRoom?.current_count ??
    aiDirect?.current_count ??
    occ?.current_count ??
    0;
  const inCount =
    liveRoom?.in_count ?? aiDirect?.in_count ?? occ?.in_count ?? 0;
  const outCount =
    liveRoom?.out_count ?? aiDirect?.out_count ?? occ?.out_count ?? 0;
  const maxCapacity = room?.max_capacity ?? occ?.max_capacity ?? 60;
  const overallDensity =
    liveRoom?.overall_density ??
    aiDirect?.overall_density ??
    occ?.overall_density ??
    0;
  const roomStatus =
    liveRoom?.room_status ??
    aiDirect?.alert_level ??
    occ?.room_status ??
    'NORMAL';
  const fps =
    aiDirect?.performance?.fps ??
    liveRoom?.inference_fps ??
    occ?.inference_fps ??
    null;
  const inferenceMs = aiDirect?.performance?.inference_ms ?? null;
  const processingMs = aiDirect?.performance?.processing_ms ?? null;

  const zones = room?.zones || [];
  const zoneMetrics = den?.zones || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">
            Live Monitoring (Giám Sát Camera & AI Thời Gian Thực)
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Hiển thị trực tiếp luồng YOLOv8 + ByteTrack từ AI Service • Không tự
            sinh bounding box giả khi camera chưa bật
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-500 dark:text-slate-400">
            Mức cảnh báo hiện tại:
          </span>
          <StatusBadge status={roomStatus} size="md" pulse />
        </div>
      </div>

      {/* Realtime Counter Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <div className="p-4 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
          <span className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
            <Users className="w-3.5 h-3.5 text-sky-500" />
            Hiện diện (Current)
          </span>
          <div className="text-2xl font-bold font-mono text-slate-900 dark:text-slate-100 mt-1">
            {currentCount}
            <span className="text-xs font-normal text-slate-400">
              /{maxCapacity}
            </span>
          </div>
        </div>

        <div className="p-4 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
          <span className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
            <ArrowDownLeft className="w-3.5 h-3.5 text-emerald-500" />
            Người đi vào (IN)
          </span>
          <div className="text-2xl font-bold font-mono text-emerald-600 dark:text-emerald-400 mt-1">
            +{inCount}
          </div>
        </div>

        <div className="p-4 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
          <span className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
            <ArrowUpRight className="w-3.5 h-3.5 text-amber-500" />
            Người đi ra (OUT)
          </span>
          <div className="text-2xl font-bold font-mono text-amber-600 dark:text-amber-400 mt-1">
            -{outCount}
          </div>
        </div>

        <div className="p-4 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
          <span className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
            <Activity className="w-3.5 h-3.5 text-sky-500" />
            Mật độ trung bình
          </span>
          <div className="text-2xl font-bold font-mono text-slate-900 dark:text-slate-100 mt-1">
            {formatDensity(overallDensity)}
            <span className="text-xs font-normal text-slate-400"> ng/m²</span>
          </div>
        </div>

        <div className="p-4 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
          <span className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
            <Gauge className="w-3.5 h-3.5 text-emerald-500" />
            Tốc độ xử lý (FPS)
          </span>
          <div className="text-2xl font-bold font-mono text-slate-900 dark:text-slate-100 mt-1">
            {fps !== null ? fps.toFixed(1) : '--'}
            <span className="text-xs font-normal text-slate-400"> FPS</span>
          </div>
        </div>

        <div className="p-4 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
          <span className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
            <Cpu className="w-3.5 h-3.5 text-violet-500" />
            Inference / Latency
          </span>
          <div className="text-lg font-bold font-mono text-slate-900 dark:text-slate-100 mt-1.5">
            {inferenceMs !== null ? `${inferenceMs.toFixed(1)} ms` : 'N/A'}
            {processingMs !== null && (
              <span className="block text-[11px] font-normal text-slate-400">
                Total: {processingMs.toFixed(1)} ms
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Main Split View: Camera Viewport (2 cols) + Live Zone List (1 col) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <LiveCameraFeed
            roomName={room?.name || selectedRoomId}
            zones={zones}
            zoneMetrics={zoneMetrics}
            fps={fps}
          />
        </div>

        <SectionCard
          title="Danh Sách Khu Vực (Polygon Zones)"
          subtitle="Số lượng người & mật độ từng vùng theo vị trí chân bounding box"
          icon={<Layers className="w-4 h-4" />}
        >
          <div className="space-y-3">
            {zoneMetrics.map((zm) => {
              const zoneConfig = zones.find((z) => z.code === zm.zone_code);
              const color = zoneConfig?.color_hex || '#0ea5e9';
              const clampedPct = Math.min(100, Math.max(0, zm.utilization_pct));

              return (
                <div
                  key={zm.zone_id}
                  className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 space-y-2.5"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span
                        className="w-3 h-3 rounded-full shrink-0"
                        style={{ backgroundColor: color }}
                      />
                      <div>
                        <h4 className="text-xs font-semibold text-slate-900 dark:text-slate-100">
                          {zm.zone_name}
                        </h4>
                        <span className="text-[11px] font-mono text-slate-500 dark:text-slate-400">
                          {zm.zone_code} • {zm.area_sqm} m²
                        </span>
                      </div>
                    </div>
                    <StatusBadge status={zm.severity} />
                  </div>

                  <div className="grid grid-cols-3 gap-2 text-xs">
                    <div className="p-2 rounded-lg bg-white dark:bg-slate-900 border border-slate-200/70 dark:border-slate-800">
                      <span className="text-[10px] text-slate-400 block">
                        Số người
                      </span>
                      <span className="font-mono font-bold text-slate-900 dark:text-slate-100">
                        {zm.person_count}/{zm.max_capacity}
                      </span>
                    </div>
                    <div className="p-2 rounded-lg bg-white dark:bg-slate-900 border border-slate-200/70 dark:border-slate-800">
                      <span className="text-[10px] text-slate-400 block">
                        Mật độ
                      </span>
                      <span className="font-mono font-bold text-sky-600 dark:text-sky-400">
                        {formatDensity(zm.density_per_sqm)} ng/m²
                      </span>
                    </div>
                    <div className="p-2 rounded-lg bg-white dark:bg-slate-900 border border-slate-200/70 dark:border-slate-800">
                      <span className="text-[10px] text-slate-400 block">
                        Lấp đầy
                      </span>
                      <span className="font-mono font-bold text-slate-900 dark:text-slate-100">
                        {formatPercentage(zm.utilization_pct)}
                      </span>
                    </div>
                  </div>

                  <div className="w-full h-1.5 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
                    <div
                      className={`h-full transition-all duration-300 ${
                        zm.severity === 'CRITICAL'
                          ? 'bg-rose-500'
                          : zm.severity === 'WARNING'
                            ? 'bg-amber-500'
                            : 'bg-emerald-500'
                      }`}
                      style={{ width: `${clampedPct}%` }}
                    />
                  </div>
                </div>
              );
            })}

            {zoneMetrics.length === 0 && (
              <div className="text-xs text-slate-500 dark:text-slate-400 text-center py-6">
                Chưa có phân vùng nào trong phòng này.
              </div>
            )}
          </div>
        </SectionCard>
      </div>
    </div>
  );
};
