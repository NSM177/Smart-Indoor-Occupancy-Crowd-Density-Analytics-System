import React, { useState } from 'react';
import {
  Camera,
  Cpu,
  Radio,
  RefreshCw,
  Volume2,
  VolumeX,
  Wifi,
  WifiOff,
} from 'lucide-react';
import {
  EmptyState,
  LoadingState,
  SectionCard,
  StatusBadge,
} from '../../components/ui/Primitives';
import {
  useDevicesQuery,
  useSendDeviceCommandMutation,
} from '../../hooks/useDomainQueries';
import { useRealtimeStore } from '../../stores/realtimeStore';
import { useUIStore } from '../../stores/uiStore';
import { DeviceCommandPayload, LedColor } from '../../types';
import { formatDateTime } from '../../utils/formatters';

export const DeviceManagementPage: React.FC = () => {
  const { selectedRoomId } = useUIStore();
  const connectionStatus = useRealtimeStore((s) => s.connectionStatus);
  const devicesQuery = useDevicesQuery(selectedRoomId);
  const sendCommandMutation = useSendDeviceCommandMutation();
  const [feedbackMsg, setFeedbackMsg] = useState<string | null>(null);

  if (devicesQuery.isLoading) {
    return <LoadingState label="Đang kiểm tra trạng thái thiết bị IoT & Camera..." />;
  }

  const devices = devicesQuery.data || [];

  const handleDispatchCommand = async (
    deviceId: string,
    payload: DeviceCommandPayload,
  ) => {
    setFeedbackMsg(null);
    try {
      const res = await sendCommandMutation.mutateAsync({
        deviceId,
        command: payload,
      });
      setFeedbackMsg(
        `Đã gửi lệnh điều khiển tới ${res.device.device_code} thông qua Backend API (LED=${res.device.led_state}, Buzzer=${
          res.device.buzzer_active ? 'ON' : 'OFF'
        }, Auto=${res.device.auto_mode ? 'ON' : 'OFF'})`,
      );
    } catch (err) {
      setFeedbackMsg(
        err instanceof Error ? err.message : 'Lỗi khi gửi lệnh điều khiển.',
      );
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">
            Device Management (Quản Lý Thiết Bị Raspberry Pi, Camera & MQTT)
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Giám sát trạng thái Online/Offline, Last Heartbeat, LED/Buzzer và
            gửi lệnh điều khiển qua Backend API (không truy cập GPIO trực tiếp)
          </p>
        </div>

        <button
          type="button"
          onClick={() => devicesQuery.refetch()}
          className="px-3.5 py-2 rounded-xl bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-xs font-semibold flex items-center gap-1.5 transition"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Làm mới trạng thái
        </button>
      </div>

      {/* Infrastructure Connectivity Banner */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <div>
            <span className="text-xs text-slate-500 dark:text-slate-400">
              Kết nối MQTT & WebSocket Bridge
            </span>
            <div className="text-sm font-bold text-slate-900 dark:text-slate-100 mt-1">
              Mosquitto Broker (Port 1883)
            </div>
            <span className="text-[11px] font-mono text-slate-400">
              occupancy/+/device/status • command
            </span>
          </div>
          <StatusBadge
            status={connectionStatus === 'CONNECTED' ? 'ONLINE' : 'OFFLINE'}
          />
        </div>

        <div className="p-4 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <div>
            <span className="text-xs text-slate-500 dark:text-slate-400">
              Sơ đồ chân BCM GPIO (Raspberry Pi 4/5)
            </span>
            <div className="text-xs font-mono font-semibold text-sky-600 dark:text-sky-400 mt-1">
              GREEN=17 (Pin 11) • YELLOW=27 (Pin 13)
            </div>
            <div className="text-xs font-mono font-semibold text-rose-500 mt-0.5">
              RED=22 (Pin 15) • BUZZER=23 (Pin 16)
            </div>
          </div>
          <Cpu className="w-6 h-6 text-violet-500" />
        </div>

        <div className="p-4 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <div>
            <span className="text-xs text-slate-500 dark:text-slate-400">
              Ngưỡng phát hiện mất kết nối (Heartbeat Timeout)
            </span>
            <div className="text-sm font-bold text-slate-900 dark:text-slate-100 mt-1">
              35 giây (Tự động chuyển OFFLINE)
            </div>
            <span className="text-[11px] text-slate-400">
              Chu kỳ heartbeat thiết bị: 10 giây
            </span>
          </div>
          <Radio className="w-6 h-6 text-emerald-500" />
        </div>
      </div>

      {feedbackMsg && (
        <div className="p-3.5 rounded-xl bg-sky-500/10 border border-sky-500/30 text-xs font-medium text-sky-700 dark:text-sky-300">
          {feedbackMsg}
        </div>
      )}

      {/* Device Cards */}
      <SectionCard
        title={`Danh Sách Thiết Bị Đã Đăng Ký (${devices.length})`}
        subtitle="Hiển thị trạng thái Raspberry Pi, Camera, LED, Buzzer và bảng điều khiển từ xa"
        icon={<Cpu className="w-4 h-4" />}
      >
        {devices.length === 0 ? (
          <EmptyState
            title="Chưa có thiết bị nào được đăng ký cho phòng này"
            description="Thiết bị sẽ tự động đăng ký khi gửi gói tin trạng thái qua MQTT."
          />
        ) : (
          <div className="space-y-4">
            {devices.map((dev) => {
              const led: LedColor = dev.led_state || 'GREEN';
              return (
                <div
                  key={dev.id}
                  className="p-5 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 space-y-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className="p-3 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-sky-500">
                        <Cpu className="w-6 h-6" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="text-base font-bold text-slate-900 dark:text-slate-100">
                            {dev.name}
                          </h4>
                          <span className="px-2 py-0.5 rounded bg-slate-200 dark:bg-slate-800 text-xs font-mono">
                            {dev.device_code}
                          </span>
                        </div>
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                          Loại: {dev.device_type} • Chế độ GPIO:{' '}
                          <strong className="font-mono">{dev.gpio_mode}</strong>{' '}
                          • Firmware: v{dev.firmware_version}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <span
                        className={`px-3 py-1 rounded-full text-xs font-semibold flex items-center gap-1.5 border ${
                          dev.is_online
                            ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30'
                            : 'bg-slate-500/10 text-slate-500 border-slate-500/30'
                        }`}
                      >
                        {dev.is_online ? (
                          <Wifi className="w-3.5 h-3.5" />
                        ) : (
                          <WifiOff className="w-3.5 h-3.5" />
                        )}
                        {dev.status}
                      </span>
                    </div>
                  </div>

                  {/* Telemetry Details Grid */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
                    <div className="p-3 rounded-lg bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800">
                      <span className="text-slate-400 flex items-center gap-1">
                        <Camera className="w-3.5 h-3.5 text-sky-500" />
                        Camera Stream & Độ phân giải
                      </span>
                      <div className="font-mono font-semibold text-slate-900 dark:text-slate-100 mt-1">
                        Source: {dev.stream_url || '0'} ({dev.resolution_width}x
                        {dev.resolution_height} @ {dev.fps_target} FPS)
                      </div>
                    </div>

                    <div className="p-3 rounded-lg bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800">
                      <span className="text-slate-400 block">
                        Last Heartbeat / Communication
                      </span>
                      <div className="font-mono font-semibold text-slate-900 dark:text-slate-100 mt-1">
                        {formatDateTime(dev.last_heartbeat)}
                      </div>
                    </div>

                    <div className="p-3 rounded-lg bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800">
                      <span className="text-slate-400 block">
                        Trạng thái Đèn Cảnh Báo (LED Status)
                      </span>
                      <div className="flex items-center gap-2 mt-1.5">
                        <span
                          className={`w-4 h-4 rounded-full ${
                            led === 'GREEN'
                              ? 'bg-emerald-400 shadow-[0_0_10px_#34d399]'
                              : 'bg-emerald-950/50'
                          }`}
                        />
                        <span
                          className={`w-4 h-4 rounded-full ${
                            led === 'YELLOW'
                              ? 'bg-amber-400 shadow-[0_0_10px_#fbbf24]'
                              : 'bg-amber-950/50'
                          }`}
                        />
                        <span
                          className={`w-4 h-4 rounded-full ${
                            led === 'RED'
                              ? 'bg-rose-500 shadow-[0_0_12px_#f43f5e] animate-pulse'
                              : 'bg-rose-950/50'
                          }`}
                        />
                        <span className="font-mono font-bold ml-1">{led}</span>
                      </div>
                    </div>

                    <div className="p-3 rounded-lg bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800">
                      <span className="text-slate-400 block">
                        Còi báo động (Buzzer) & Chế độ
                      </span>
                      <div className="flex items-center justify-between mt-1.5">
                        <span
                          className={`px-2 py-0.5 rounded font-semibold flex items-center gap-1 ${
                            dev.buzzer_active
                              ? 'bg-rose-600 text-white'
                              : 'bg-slate-100 dark:bg-slate-800 text-slate-500'
                          }`}
                        >
                          {dev.buzzer_active ? (
                            <>
                              <Volume2 className="w-3.5 h-3.5" /> ACTIVE
                            </>
                          ) : (
                            <>
                              <VolumeX className="w-3.5 h-3.5" /> OFF
                            </>
                          )}
                        </span>
                        <span className="font-mono text-[11px] text-sky-500">
                          {dev.auto_mode ? 'AUTO MODE' : 'MANUAL OVERRIDE'}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Remote Command Dispatch Controls via Backend API */}
                  <div className="pt-3 border-t border-slate-200 dark:border-slate-800 flex flex-wrap items-center justify-between gap-3">
                    <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
                      Điều khiển thiết bị qua Backend REST API (
                      <code className="font-mono">
                        POST /api/v1/devices/{dev.device_code}/commands
                      </code>
                      ):
                    </span>

                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        disabled={sendCommandMutation.isPending}
                        onClick={() =>
                          handleDispatchCommand(dev.device_code, {
                            led_state: 'GREEN',
                            buzzer_active: false,
                            auto_mode: false,
                          })
                        }
                        className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold transition"
                      >
                        Bật LED Xanh
                      </button>

                      <button
                        type="button"
                        disabled={sendCommandMutation.isPending}
                        onClick={() =>
                          handleDispatchCommand(dev.device_code, {
                            led_state: 'YELLOW',
                            buzzer_active: false,
                            auto_mode: false,
                          })
                        }
                        className="px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-semibold transition"
                      >
                        Bật LED Vàng
                      </button>

                      <button
                        type="button"
                        disabled={sendCommandMutation.isPending}
                        onClick={() =>
                          handleDispatchCommand(dev.device_code, {
                            led_state: 'RED',
                            buzzer_active: true,
                            auto_mode: false,
                          })
                        }
                        className="px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold transition"
                      >
                        Báo động (LED Đỏ + Còi)
                      </button>

                      <button
                        type="button"
                        disabled={sendCommandMutation.isPending}
                        onClick={() =>
                          handleDispatchCommand(dev.device_code, {
                            led_state: 'GREEN',
                            buzzer_active: false,
                            auto_mode: true,
                          })
                        }
                        className="px-3 py-1.5 rounded-lg bg-slate-200 dark:bg-slate-800 hover:bg-sky-600 hover:text-white text-xs font-semibold transition"
                      >
                        Khôi phục Auto Mode
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </SectionCard>
    </div>
  );
};
