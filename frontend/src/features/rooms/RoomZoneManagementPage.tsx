import React, { useEffect, useState } from 'react';
import {
  Building2,
  Check,
  Plus,
  Save,
  Trash2,
} from 'lucide-react';
import { PolygonZoneDrawer } from '../../components/monitoring/SpatialWidgets';
import {
  LoadingState,
  ModalDialog,
  SectionCard,
} from '../../components/ui/Primitives';
import {
  useCreateRoomMutation,
  useCreateZoneMutation,
  useDeleteRoomMutation,
  useDeleteZoneMutation,
  useRoomDetailQuery,
  useRoomsQuery,
  useUpdateRoomMutation,
} from '../../hooks/useDomainQueries';
import { useAuthStore } from '../../stores/authStore';
import { useUIStore } from '../../stores/uiStore';
import { ZoneCreatePayload } from '../../types';

export const RoomZoneManagementPage: React.FC = () => {
  const { selectedRoomId, setSelectedRoomId } = useUIStore();
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === 'ADMIN';

  const roomsQuery = useRoomsQuery();
  const roomDetailQuery = useRoomDetailQuery(selectedRoomId);
  const createRoomMutation = useCreateRoomMutation();
  const updateRoomMutation = useUpdateRoomMutation();
  const deleteRoomMutation = useDeleteRoomMutation();
  const createZoneMutation = useCreateZoneMutation();
  const deleteZoneMutation = useDeleteZoneMutation();

  const room = roomDetailQuery.data;

  // Room Update Form State
  const [roomName, setRoomName] = useState('');
  const [roomDesc, setRoomDesc] = useState('');
  const [areaSqm, setAreaSqm] = useState<number>(120);
  const [maxCapacity, setMaxCapacity] = useState<number>(60);
  const [warnRatio, setWarnRatio] = useState<number>(0.75);
  const [critDensity, setCritDensity] = useState<number>(0.8);
  const [roomFeedback, setRoomFeedback] = useState<string | null>(null);
  const [roomError, setRoomError] = useState<string | null>(null);

  // Create New Room Modal State
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [newCode, setNewCode] = useState('');
  const [newName, setNewName] = useState('');
  const [newArea, setNewArea] = useState<number>(100);
  const [newCap, setNewCap] = useState<number>(50);
  const [createErr, setCreateErr] = useState<string | null>(null);

  useEffect(() => {
    if (room) {
      setRoomName(room.name);
      setRoomDesc(room.description || '');
      setAreaSqm(room.area_sqm);
      setMaxCapacity(room.max_capacity);
      setWarnRatio(room.warning_threshold_ratio);
      setCritDensity(room.critical_density_per_sqm);
    }
  }, [room]);

  if (roomsQuery.isLoading || roomDetailQuery.isLoading) {
    return <LoadingState label="Đang tải cấu hình Phòng & Polygon Zones..." />;
  }

  const handleUpdateRoom = async (e: React.FormEvent) => {
    e.preventDefault();
    setRoomFeedback(null);
    setRoomError(null);
    if (!room) return;
    if (areaSqm <= 1) {
      setRoomError('Diện tích phòng phải lớn hơn 1 m².');
      return;
    }
    if (maxCapacity < 1) {
      setRoomError('Sức chứa tối đa phải từ 1 người trở lên.');
      return;
    }

    try {
      await updateRoomMutation.mutateAsync({
        roomId: room.id,
        payload: {
          name: roomName.trim(),
          description: roomDesc.trim(),
          area_sqm: Number(areaSqm),
          max_capacity: Number(maxCapacity),
          warning_threshold_ratio: Number(warnRatio),
          critical_density_per_sqm: Number(critDensity),
        },
      });
      setRoomFeedback(
        'Đã lưu cấu hình phòng và đồng bộ xuống AI Service qua MQTT!',
      );
    } catch (err) {
      setRoomError(
        err instanceof Error ? err.message : 'Lỗi khi cập nhật phòng.',
      );
    }
  };

  const handleCreateRoom = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateErr(null);
    if (!newCode.trim() || !newName.trim()) {
      setCreateErr('Vui lòng nhập Mã phòng và Tên phòng.');
      return;
    }
    try {
      const created = await createRoomMutation.mutateAsync({
        code: newCode.trim().toLowerCase(),
        name: newName.trim(),
        area_sqm: Number(newArea),
        max_capacity: Number(newCap),
        warning_threshold_ratio: 0.75,
        critical_density_per_sqm: 0.8,
      });
      setCreateModalOpen(false);
      setSelectedRoomId(created.code);
      setNewCode('');
      setNewName('');
    } catch (err) {
      setCreateErr(
        err instanceof Error
          ? err.message
          : 'Không thể tạo phòng (Yêu cầu quyền ADMIN).',
      );
    }
  };

  const handleDeleteCurrentRoom = async () => {
    if (!room) return;
    if (
      !window.confirm(
        `Bạn có chắc chắn muốn xóa phòng "${room.name}" (${room.code})?`,
      )
    ) {
      return;
    }
    try {
      await deleteRoomMutation.mutateAsync(room.id);
      const remaining = (roomsQuery.data || []).filter((r) => r.id !== room.id);
      if (remaining.length > 0) {
        setSelectedRoomId(remaining[0].code);
      }
    } catch (err) {
      setRoomError(
        err instanceof Error
          ? err.message
          : 'Không thể xóa phòng (Yêu cầu quyền ADMIN).',
      );
    }
  };

  const handleCreateZone = async (payload: ZoneCreatePayload) => {
    if (!room) return;
    await createZoneMutation.mutateAsync({
      roomId: room.id,
      payload,
    });
  };

  const handleDeleteZone = async (zoneId: string) => {
    await deleteZoneMutation.mutateAsync(zoneId);
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">
            Room & Zone Management (Quản Lý Phòng & Phân Vùng Đa Giác)
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Thiết lập diện tích thực tế, sức chứa tối đa, ngưỡng mật độ và vẽ
            tọa độ Polygon Zones
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setCreateModalOpen(true)}
            className="px-3.5 py-2 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold flex items-center gap-1.5 transition"
          >
            <Plus className="w-4 h-4" />
            Tạo Phòng Mới {isAdmin ? '' : '(Admin)'}
          </button>
        </div>
      </div>

      {/* Room Configuration Form */}
      <SectionCard
        title={`Cấu Hình Thông Số Phòng: ${room?.name || selectedRoomId}`}
        subtitle={`Mã phòng: ${room?.code || selectedRoomId} • ID: ${room?.id || ''}`}
        icon={<Building2 className="w-4 h-4" />}
        action={
          isAdmin &&
          (roomsQuery.data?.length || 0) > 1 && (
            <button
              type="button"
              onClick={handleDeleteCurrentRoom}
              className="px-3 py-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-600 dark:text-rose-400 text-xs font-semibold flex items-center gap-1"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Xóa phòng này
            </button>
          )
        }
      >
        <form onSubmit={handleUpdateRoom} className="space-y-4">
          {roomFeedback && (
            <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-xs text-emerald-600 dark:text-emerald-400 flex items-center gap-2">
              <Check className="w-4 h-4" />
              {roomFeedback}
            </div>
          )}
          {roomError && (
            <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-xs text-rose-600 dark:text-rose-400">
              {roomError}
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">
                Tên phòng (Room Name)
              </label>
              <input
                type="text"
                required
                value={roomName}
                onChange={(e) => setRoomName(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">
                Diện tích sàn hiệu chuẩn (m²)
              </label>
              <input
                type="number"
                step="0.5"
                min="2"
                required
                value={areaSqm}
                onChange={(e) => setAreaSqm(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm font-mono"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">
                Sức chứa tối đa (Max Capacity - người)
              </label>
              <input
                type="number"
                min="1"
                required
                value={maxCapacity}
                onChange={(e) => setMaxCapacity(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm font-mono"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">
                Tỷ lệ cảnh báo sớm (Warning Ratio 0.1 – 1.0)
              </label>
              <input
                type="number"
                step="0.05"
                min="0.1"
                max="1.0"
                required
                value={warnRatio}
                onChange={(e) => setWarnRatio(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm font-mono"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">
                Ngưỡng mật độ nguy hiểm (Critical Density người/m²)
              </label>
              <input
                type="number"
                step="0.05"
                min="0.05"
                required
                value={critDensity}
                onChange={(e) => setCritDensity(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm font-mono"
              />
            </div>

            <div className="flex items-end">
              <button
                type="submit"
                disabled={updateRoomMutation.isPending}
                className="w-full py-2 px-4 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold flex items-center justify-center gap-2 transition"
              >
                <Save className="w-4 h-4" />
                {updateRoomMutation.isPending
                  ? 'Đang lưu...'
                  : 'Cập nhật Cấu hình Phòng'}
              </button>
            </div>
          </div>
        </form>
      </SectionCard>

      {/* Interactive Polygon Zone Editor */}
      <PolygonZoneDrawer
        zones={room?.zones || []}
        onCreateZone={handleCreateZone}
        onDeleteZone={handleDeleteZone}
      />

      {/* Modal Create Room */}
      <ModalDialog
        open={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
        title="Tạo Phòng Giám Sát Mới"
      >
        <form onSubmit={handleCreateRoom} className="space-y-4">
          {createErr && (
            <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-xs text-rose-500">
              {createErr}
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">
              Mã phòng (Room Code — duy nhất)
            </label>
            <input
              type="text"
              placeholder="VD: room2"
              required
              value={newCode}
              onChange={(e) => setNewCode(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm font-mono"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">
              Tên phòng
            </label>
            <input
              type="text"
              placeholder="VD: Hội trường Tầng 2"
              required
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-500 mb-1">
                Diện tích (m²)
              </label>
              <input
                type="number"
                min="5"
                value={newArea}
                onChange={(e) => setNewArea(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-500 mb-1">
                Sức chứa (người)
              </label>
              <input
                type="number"
                min="1"
                value={newCap}
                onChange={(e) => setNewCap(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm"
              />
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setCreateModalOpen(false)}
              className="px-4 py-2 rounded-lg bg-slate-100 dark:bg-slate-800 text-xs font-medium"
            >
              Hủy
            </button>
            <button
              type="submit"
              disabled={createRoomMutation.isPending}
              className="px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold"
            >
              Tạo Phòng
            </button>
          </div>
        </form>
      </ModalDialog>
    </div>
  );
};
