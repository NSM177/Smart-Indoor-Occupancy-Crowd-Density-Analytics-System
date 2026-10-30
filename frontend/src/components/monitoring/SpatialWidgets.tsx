import React, { useRef, useState } from 'react';
import {
  Camera,
  Check,
  Flame,
  Layers,
  MapPin,
  Plus,
  RefreshCw,
  Trash2,
  Undo2,
  VideoOff,
} from 'lucide-react';
import { AI_SERVICE_URL } from '../../lib/axios';
import {
  Point2D,
  SeverityLevel,
  ZoneCreatePayload,
  ZoneDensitySnapshot,
  ZoneEntity,
} from '../../types';
import {
  computePolygonCentroid,
  validatePolygonCoordinates,
} from '../../utils/polygon';

// ============================================================================
// 1. LiveCameraFeed: Displays real MJPEG stream from AI Engine.
//    NEVER fabricates fake bounding boxes when stream is unavailable.
// ============================================================================
interface LiveCameraFeedProps {
  roomName: string;
  zones: ZoneEntity[];
  zoneMetrics: ZoneDensitySnapshot[];
  fps?: number | null;
}

export const LiveCameraFeed: React.FC<LiveCameraFeedProps> = ({
  roomName,
  zones,
  zoneMetrics,
  fps,
}) => {
  const [streamError, setStreamError] = useState(false);
  const [showZonesOverlay, setShowZonesOverlay] = useState(true);
  const [reloadNonce, setReloadNonce] = useState(0);

  const mjpegUrl = `${AI_SERVICE_URL}/stream.mjpg?t=${reloadNonce}`;

  return (
    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden shadow-xs">
      <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span
            className={`w-2.5 h-2.5 rounded-full ${
              streamError ? 'bg-amber-500' : 'bg-emerald-500 animate-pulse'
            }`}
          />
          <Camera className="w-4 h-4 text-sky-500" />
          <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            {roomName} — AI Vision Stream
          </span>
          {fps !== null && fps !== undefined && fps > 0 && (
            <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 text-xs font-mono">
              {fps.toFixed(1)} FPS
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowZonesOverlay((v) => !v)}
            className={`px-2.5 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition ${
              showZonesOverlay
                ? 'bg-sky-600 text-white'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            Lớp phủ Polygon ({zones.length})
          </button>
          <button
            type="button"
            onClick={() => {
              setStreamError(false);
              setReloadNonce((n) => n + 1);
            }}
            className="px-2.5 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-xs font-medium flex items-center gap-1"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Tải lại Stream
          </button>
        </div>
      </div>

      <div className="relative aspect-video bg-slate-950 flex items-center justify-center overflow-hidden">
        {!streamError ? (
          <img
            src={mjpegUrl}
            alt="AI Computer Vision Stream"
            className="w-full h-full object-contain"
            onError={() => setStreamError(true)}
          />
        ) : (
          <div className="w-full h-full relative flex flex-col items-center justify-center p-6 text-center">
            <div className="relative z-10 bg-slate-900/95 border border-slate-800 rounded-xl px-6 py-5 max-w-md shadow-xl">
              <div className="w-10 h-10 rounded-full bg-slate-800 text-amber-400 flex items-center justify-center mx-auto mb-3">
                <VideoOff className="w-5 h-5" />
              </div>
              <p className="text-sm font-semibold text-slate-100">
                Luồng MJPEG từ AI Engine hiện chưa kết nối
              </p>
              <p className="text-xs text-slate-400 mt-1.5">
                Endpoint <code className="text-sky-400">{AI_SERVICE_URL}/stream.mjpg</code>{' '}
                chưa phát luồng video. Hệ thống giữ nguyên dữ liệu thật từ
                WebSocket/Database và không tự vẽ bounding box giả.
              </p>
              <button
                type="button"
                onClick={() => {
                  setStreamError(false);
                  setReloadNonce((n) => n + 1);
                }}
                className="mt-4 px-3.5 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-xs font-semibold text-white transition"
              >
                Kết nối lại Camera Stream
              </button>
            </div>
          </div>
        )}

        {/* Calibrated Polygon Zone Overlay */}
        {showZonesOverlay && zones.length > 0 && (
          <svg
            viewBox="0 0 1000 562"
            className="w-full h-full absolute inset-0 pointer-events-none"
            preserveAspectRatio="none"
          >
            {zones.map((z) => {
              const pts = z.polygon_coordinates
                .map((p) => `${p.x * 1000},${p.y * 562}`)
                .join(' ');
              const center = computePolygonCentroid(z.polygon_coordinates);
              const metric = zoneMetrics.find((m) => m.zone_code === z.code);
              return (
                <g key={z.id}>
                  <polygon
                    points={pts}
                    fill={`${z.color_hex}22`}
                    stroke={z.color_hex}
                    strokeWidth="2.5"
                  />
                  <text
                    x={center.x * 1000}
                    y={center.y * 562}
                    textAnchor="middle"
                    fill="#f8fafc"
                    fontSize="15"
                    fontWeight="bold"
                  >
                    {z.code}: {metric?.person_count ?? 0}/{z.max_capacity} người
                  </text>
                </g>
              );
            })}
          </svg>
        )}
      </div>
    </div>
  );
};

// ============================================================================
// 2. InteractiveFloorPlan: Spatial Floor Plan + Polygon Zones + Gaussian Heatmap
// ============================================================================
interface InteractiveFloorPlanProps {
  zones: ZoneEntity[];
  zoneMetrics: ZoneDensitySnapshot[];
  heatmapGrid?: number[][];
  showSampleBlueprint?: boolean;
}

function getSeverityStrokeAndFill(
  severity: SeverityLevel | undefined,
  fallbackHex: string,
): { stroke: string; fill: string } {
  if (severity === 'CRITICAL') {
    return { stroke: '#f43f5e', fill: 'rgba(244, 63, 94, 0.28)' };
  }
  if (severity === 'WARNING') {
    return { stroke: '#f59e0b', fill: 'rgba(245, 158, 11, 0.25)' };
  }
  return { stroke: fallbackHex || '#10b981', fill: 'rgba(16, 185, 129, 0.20)' };
}

export const InteractiveFloorPlan: React.FC<InteractiveFloorPlanProps> = ({
  zones,
  zoneMetrics,
  heatmapGrid,
  showSampleBlueprint = true,
}) => {
  const [showHeatmap, setShowHeatmap] = useState(true);

  // Build synthetic visualization heatmap from zone densities if AI raw matrix isn't streaming yet
  const hasRawHeatmap = Boolean(heatmapGrid && heatmapGrid.length > 0);

  return (
    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 shadow-xs">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <MapPin className="w-4 h-4 text-sky-500" />
            Sơ Đồ Mặt Bằng Không Gian & Mật Độ Theo Vùng (Spatial Density Map)
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Màu sắc phân vùng tự động chuyển đổi theo mức NORMAL (Xanh), WARNING (Vàng) và CRITICAL (Đỏ).
          </p>
        </div>

        <button
          type="button"
          onClick={() => setShowHeatmap((v) => !v)}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition ${
            showHeatmap
              ? 'bg-orange-600 text-white'
              : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300'
          }`}
        >
          <Flame className="w-3.5 h-3.5" />
          {showHeatmap ? 'Đang bật lớp phủ Heatmap' : 'Bật lớp phủ Heatmap'}
        </button>
      </div>

      <div className="relative aspect-video bg-slate-950 border border-slate-800 rounded-xl overflow-hidden">
        {/* Optional raw 2D heatmap grid from AI Engine */}
        {showHeatmap && hasRawHeatmap && heatmapGrid && (
          <div
            className="absolute inset-0 grid opacity-60 pointer-events-none"
            style={{
              gridTemplateRows: `repeat(${heatmapGrid.length}, minmax(0, 1fr))`,
              gridTemplateColumns: `repeat(${heatmapGrid[0]?.length || 32}, minmax(0, 1fr))`,
            }}
          >
            {heatmapGrid.map((row, rIdx) =>
              row.map((val, cIdx) => {
                const v = Math.min(1, Math.max(0, val));
                const bg =
                  v < 0.05
                    ? 'transparent'
                    : v < 0.4
                      ? `rgba(14, 165, 233, ${v * 0.8})`
                      : v < 0.75
                        ? `rgba(245, 158, 11, ${v * 0.85})`
                        : `rgba(244, 63, 94, ${v * 0.9})`;
                return (
                  <div key={`${rIdx}-${cIdx}`} style={{ backgroundColor: bg }} />
                );
              }),
            )}
          </div>
        )}

        <svg
          viewBox="0 0 1000 562"
          className="w-full h-full relative z-10"
          preserveAspectRatio="none"
        >
          <defs>
            <pattern
              id="floorBlueprintGrid"
              width="50"
              height="50"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M 50 0 L 0 0 0 50"
                fill="none"
                stroke="rgba(148,163,184,0.12)"
                strokeWidth="1"
              />
            </pattern>
            <radialGradient id="heatHotspotCritical" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#f43f5e" stopOpacity="0.55" />
              <stop offset="55%" stopColor="#f59e0b" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#0f172a" stopOpacity="0" />
            </radialGradient>
            <radialGradient id="heatHotspotNormal" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#0ea5e9" stopOpacity="0.45" />
              <stop offset="65%" stopColor="#10b981" stopOpacity="0.18" />
              <stop offset="100%" stopColor="#0f172a" stopOpacity="0" />
            </radialGradient>
          </defs>

          <rect width="1000" height="562" fill="url(#floorBlueprintGrid)" />

          {/* Sample Architectural Floor Plan Blueprint Markers in Dev Mode */}
          {showSampleBlueprint && (
            <g stroke="rgba(148,163,184,0.28)" strokeWidth="2" fill="none">
              <rect x="15" y="15" width="970" height="532" rx="8" />
              <text
                x="40"
                y="42"
                fill="rgba(148,163,184,0.55)"
                fontSize="12"
                fontFamily="monospace"
              >
                ENTRANCE GATE (IN/OUT VIRTUAL LINE)
              </text>
              <line
                x1="15"
                y1="281"
                x2="985"
                y2="281"
                stroke="rgba(56,189,248,0.25)"
                strokeDasharray="8 6"
              />
            </g>
          )}

          {/* Zone Polygons & Radial Gaussian Heat Blobs */}
          {zones.map((z) => {
            const pts = z.polygon_coordinates
              .map((p) => `${p.x * 1000},${p.y * 562}`)
              .join(' ');
            const center = computePolygonCentroid(z.polygon_coordinates);
            const metric = zoneMetrics.find((m) => m.zone_code === z.code);
            const { stroke, fill } = getSeverityStrokeAndFill(
              metric?.severity,
              z.color_hex,
            );
            const personCount = metric?.person_count ?? 0;
            const densityVal = metric?.density_per_sqm ?? 0;
            const utilPct = metric?.utilization_pct ?? 0;

            return (
              <g key={z.id}>
                {showHeatmap && !hasRawHeatmap && personCount > 0 && (
                  <circle
                    cx={center.x * 1000}
                    cy={center.y * 562}
                    r={Math.min(220, 70 + personCount * 6)}
                    fill={
                      metric?.severity === 'CRITICAL' ||
                      metric?.severity === 'WARNING'
                        ? 'url(#heatHotspotCritical)'
                        : 'url(#heatHotspotNormal)'
                    }
                  />
                )}
                <polygon
                  points={pts}
                  fill={fill}
                  stroke={stroke}
                  strokeWidth="3"
                />
                <rect
                  x={center.x * 1000 - 95}
                  y={center.y * 562 - 36}
                  width="190"
                  height="72"
                  rx="8"
                  fill="rgba(15, 23, 42, 0.88)"
                  stroke={stroke}
                  strokeWidth="1.5"
                />
                <text
                  x={center.x * 1000}
                  y={center.y * 562 - 14}
                  textAnchor="middle"
                  fill="#f8fafc"
                  fontSize="13"
                  fontWeight="bold"
                >
                  {z.code} • {personCount}/{z.max_capacity} người
                </text>
                <text
                  x={center.x * 1000}
                  y={center.y * 562 + 6}
                  textAnchor="middle"
                  fill="#38bdf8"
                  fontSize="12"
                  fontFamily="monospace"
                >
                  {densityVal.toFixed(2)} ng/m² ({utilPct.toFixed(0)}%)
                </text>
                <text
                  x={center.x * 1000}
                  y={center.y * 562 + 24}
                  textAnchor="middle"
                  fill={stroke}
                  fontSize="11"
                  fontWeight="bold"
                >
                  {metric?.severity || 'NORMAL'} ({z.area_sqm} m²)
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Legend */}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500 dark:text-slate-400">
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-xs bg-emerald-500 inline-block" />
            NORMAL (An toàn)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-xs bg-amber-500 inline-block" />
            WARNING (Gần ngưỡng)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-xs bg-rose-500 inline-block" />
            CRITICAL (Quá tải mật độ)
          </span>
        </div>
        <span>Tọa độ chuẩn hóa [0.000 – 1.000]</span>
      </div>
    </div>
  );
};

// ============================================================================
// 3. PolygonZoneDrawer: Interactive Polygon Zone Editor with Form Validation
// ============================================================================
const ZONE_COLORS = [
  '#3B82F6',
  '#10B981',
  '#F59E0B',
  '#EC4899',
  '#8B5CF6',
  '#06B6D4',
];

interface PolygonZoneDrawerProps {
  zones: ZoneEntity[];
  onCreateZone: (payload: ZoneCreatePayload) => Promise<void>;
  onDeleteZone: (zoneId: string) => Promise<void>;
}

export const PolygonZoneDrawer: React.FC<PolygonZoneDrawerProps> = ({
  zones,
  onCreateZone,
  onDeleteZone,
}) => {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [draftPoints, setDraftPoints] = useState<Point2D[]>([]);
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [areaSqm, setAreaSqm] = useState<number>(30);
  const [maxCapacity, setMaxCapacity] = useState<number>(15);
  const [warningDensity, setWarningDensity] = useState<number>(0.5);
  const [criticalDensity, setCriticalDensity] = useState<number>(0.8);
  const [colorHex, setColorHex] = useState<string>(ZONE_COLORS[0]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSvgClick = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const x = Number(
      Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width)).toFixed(4),
    );
    const y = Number(
      Math.min(1, Math.max(0, (e.clientY - rect.top) / rect.height)).toFixed(4),
    );
    setDraftPoints((prev) => [...prev, { x, y }]);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    if (!name.trim() || !code.trim()) {
      setErrorMessage('Vui lòng nhập đầy đủ Tên khu vực và Mã vùng (Code).');
      return;
    }
    const polyErr = validatePolygonCoordinates(draftPoints);
    if (polyErr) {
      setErrorMessage(polyErr);
      return;
    }
    if (areaSqm <= 0.5) {
      setErrorMessage('Diện tích hiệu chuẩn thực tế phải lớn hơn 0.5 m².');
      return;
    }
    if (warningDensity >= criticalDensity) {
      setErrorMessage(
        'Ngưỡng mật độ WARNING phải nhỏ hơn ngưỡng mật độ CRITICAL.',
      );
      return;
    }

    setSubmitting(true);
    try {
      await onCreateZone({
        name: name.trim(),
        code: code.trim().toUpperCase(),
        polygon_coordinates: draftPoints,
        area_sqm: Number(areaSqm),
        max_capacity: Number(maxCapacity),
        warning_density: Number(warningDensity),
        critical_density: Number(criticalDensity),
        color_hex: colorHex,
      });
      setDraftPoints([]);
      setName('');
      setCode('');
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : 'Không thể tạo Polygon Zone.',
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <div>
            <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              Bản Đồ Vẽ Đa Giác (Click chuột trên mặt bằng để chấm đỉnh Zone)
            </h4>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Đã chấm {draftPoints.length} đỉnh (cần tối thiểu 3 đỉnh).
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={draftPoints.length === 0}
              onClick={() => setDraftPoints((p) => p.slice(0, -1))}
              className="px-2.5 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 text-xs font-medium text-slate-700 dark:text-slate-200 disabled:opacity-40 flex items-center gap-1"
            >
              <Undo2 className="w-3.5 h-3.5" />
              Hoàn tác
            </button>
            <button
              type="button"
              disabled={draftPoints.length === 0}
              onClick={() => setDraftPoints([])}
              className="px-2.5 py-1.5 rounded-lg bg-rose-500/10 text-xs font-medium text-rose-600 dark:text-rose-400 disabled:opacity-40"
            >
              Xóa các đỉnh đang vẽ
            </button>
          </div>
        </div>

        <div className="relative aspect-video bg-slate-950 border border-slate-800 rounded-xl overflow-hidden cursor-crosshair">
          <svg
            ref={svgRef}
            onClick={handleSvgClick}
            viewBox="0 0 1000 562"
            className="w-full h-full select-none"
            preserveAspectRatio="none"
          >
            <defs>
              <pattern
                id="editorGrid"
                width="50"
                height="50"
                patternUnits="userSpaceOnUse"
              >
                <path
                  d="M 50 0 L 0 0 0 50"
                  fill="none"
                  stroke="rgba(148,163,184,0.14)"
                  strokeWidth="1"
                />
              </pattern>
            </defs>
            <rect width="1000" height="562" fill="url(#editorGrid)" />

            {zones.map((z) => {
              const pts = z.polygon_coordinates
                .map((p) => `${p.x * 1000},${p.y * 562}`)
                .join(' ');
              const center = computePolygonCentroid(z.polygon_coordinates);
              return (
                <g key={z.id}>
                  <polygon
                    points={pts}
                    fill={`${z.color_hex}30`}
                    stroke={z.color_hex}
                    strokeWidth="2.5"
                  />
                  <text
                    x={center.x * 1000}
                    y={center.y * 562}
                    textAnchor="middle"
                    fill="#f8fafc"
                    fontSize="14"
                    fontWeight="bold"
                  >
                    {z.code} ({z.area_sqm}m²)
                  </text>
                </g>
              );
            })}

            {draftPoints.length > 0 && (
              <g>
                <polygon
                  points={draftPoints
                    .map((p) => `${p.x * 1000},${p.y * 562}`)
                    .join(' ')}
                  fill={`${colorHex}40`}
                  stroke={colorHex}
                  strokeWidth="2.5"
                  strokeDasharray="6 4"
                />
                {draftPoints.map((pt, idx) => (
                  <g key={idx}>
                    <circle
                      cx={pt.x * 1000}
                      cy={pt.y * 562}
                      r="6"
                      fill={colorHex}
                      stroke="#ffffff"
                      strokeWidth="2"
                    />
                    <text
                      x={pt.x * 1000 + 8}
                      y={pt.y * 562 - 6}
                      fill="#e2e8f0"
                      fontSize="12"
                    >
                      P{idx + 1}
                    </text>
                  </g>
                ))}
              </g>
            )}
          </svg>
        </div>

        {/* Existing Zones Table */}
        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-2.5">
          {zones.map((z) => (
            <div
              key={z.id}
              className="p-3 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 flex items-center justify-between"
            >
              <div className="flex items-center gap-2.5">
                <span
                  className="w-3.5 h-3.5 rounded-full shrink-0"
                  style={{ backgroundColor: z.color_hex }}
                />
                <div>
                  <div className="text-xs font-semibold text-slate-900 dark:text-slate-100">
                    {z.name} ({z.code})
                  </div>
                  <div className="text-[11px] text-slate-500 dark:text-slate-400">
                    {z.area_sqm} m² • Max {z.max_capacity} người • Ngưỡng:{' '}
                    {z.warning_density}/{z.critical_density} ng/m²
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => onDeleteZone(z.id)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-rose-500/10"
                title="Xóa vùng"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Create Zone Form */}
      <form
        onSubmit={handleSubmit}
        className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 flex flex-col justify-between"
      >
        <div className="space-y-4">
          <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <Plus className="w-4 h-4 text-emerald-500" />
            Thêm Polygon Zone Mới
          </h4>

          {errorMessage && (
            <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-xs text-rose-600 dark:text-rose-300">
              {errorMessage}
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">
              Tên khu vực (Zone Name)
            </label>
            <input
              type="text"
              placeholder="VD: Zone D - Khu vực Hội thảo"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm text-slate-900 dark:text-slate-100"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">
                Mã vùng (Zone Code)
              </label>
              <input
                type="text"
                placeholder="ZONE_D"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm font-mono text-slate-900 dark:text-slate-100"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">
                Diện tích thực tế (m²)
              </label>
              <input
                type="number"
                step="0.5"
                min="1"
                value={areaSqm}
                onChange={(e) => setAreaSqm(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm text-slate-900 dark:text-slate-100"
              />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2.5">
            <div>
              <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">
                Sức chứa
              </label>
              <input
                type="number"
                min="1"
                value={maxCapacity}
                onChange={(e) => setMaxCapacity(Number(e.target.value))}
                className="w-full px-2.5 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm text-slate-900 dark:text-slate-100"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">
                Warning (ng/m²)
              </label>
              <input
                type="number"
                step="0.05"
                min="0.05"
                value={warningDensity}
                onChange={(e) => setWarningDensity(Number(e.target.value))}
                className="w-full px-2.5 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm text-slate-900 dark:text-slate-100"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">
                Critical (ng/m²)
              </label>
              <input
                type="number"
                step="0.05"
                min="0.1"
                value={criticalDensity}
                onChange={(e) => setCriticalDensity(Number(e.target.value))}
                className="w-full px-2.5 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm text-slate-900 dark:text-slate-100"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1.5">
              Màu nhận diện vùng
            </label>
            <div className="flex items-center gap-2">
              {ZONE_COLORS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setColorHex(c)}
                  className={`w-7 h-7 rounded-full border-2 transition ${
                    colorHex === c
                      ? 'border-slate-900 dark:border-white scale-110'
                      : 'border-transparent opacity-70'
                  }`}
                  style={{ backgroundColor: c }}
                />
              ))}
            </div>
          </div>
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="mt-6 w-full py-2.5 px-4 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white text-sm font-semibold flex items-center justify-center gap-2 transition"
        >
          <Check className="w-4 h-4" />
          {submitting ? 'Đang lưu cấu hình...' : 'Lưu Polygon Zone'}
        </button>
      </form>
    </div>
  );
};
