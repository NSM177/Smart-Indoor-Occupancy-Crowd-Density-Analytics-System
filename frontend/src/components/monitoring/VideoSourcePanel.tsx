import React, { useRef, useState } from 'react';
import { Camera, Laptop, Upload, Video } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import {
  useSelectVideoSourceMutation,
  useVideoSourceQuery,
} from '../../hooks/useDomainQueries';
import { browserCamera, useBrowserCameraStore } from '../../lib/browserCamera';
import {
  VideoSourceMode,
  videoSourceService,
} from '../../services/videoSourceService';
import { useAuthStore } from '../../stores/authStore';

const DEFAULT_MAX_UPLOAD_MB = 500;

function optionClass(active: boolean): string {
  return `px-3 py-2 rounded-lg text-xs font-medium flex items-center gap-1.5 transition disabled:opacity-50 disabled:cursor-not-allowed ${
    active
      ? 'bg-sky-600 text-white'
      : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'
  }`;
}

/**
 * Chooses what the AI pipeline analyses: the configured camera (default), an
 * uploaded video, or the webcam of this laptop. Results keep flowing through the
 * normal stream, counters and dashboards.
 */
export const VideoSourcePanel: React.FC = () => {
  const queryClient = useQueryClient();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const cameraStatus = useBrowserCameraStore((s) => s.status);
  const cameraError = useBrowserCameraStore((s) => s.error);
  const sourceQuery = useVideoSourceQuery();
  const selectMutation = useSelectVideoSourceMutation();

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadPercent, setUploadPercent] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const status = sourceQuery.data;
  const mode: VideoSourceMode = status?.mode ?? 'default';
  const maxUploadMb = status?.max_upload_mb ?? DEFAULT_MAX_UPLOAD_MB;
  const uploading = uploadPercent !== null;
  const cameraActive = cameraStatus !== 'idle';
  const busy = uploading || selectMutation.isPending || cameraStatus === 'starting';
  const controlsDisabled = !isAuthenticated || !status || busy;

  const selectSource = async (next: VideoSourceMode) => {
    setActionError(null);
    browserCamera.stop();
    try {
      await selectMutation.mutateAsync(next);
    } catch (error) {
      setActionError((error as Error).message);
    }
  };

  const startLaptopCamera = async () => {
    setActionError(null);
    // Open the camera first so a denied permission leaves the current source running
    if (!(await browserCamera.openCamera())) return;
    try {
      await selectMutation.mutateAsync('browser');
      browserCamera.startStreaming();
    } catch (error) {
      browserCamera.stop();
      setActionError((error as Error).message);
    }
  };

  const handleFileChosen = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setActionError(null);
    if (file.size > maxUploadMb * 1024 * 1024) {
      setActionError(`Video vượt quá giới hạn ${maxUploadMb} MB.`);
      return;
    }
    browserCamera.stop();
    setUploadPercent(0);
    try {
      await videoSourceService.uploadVideo(file, setUploadPercent);
      await queryClient.invalidateQueries({ queryKey: ['video-source'] });
    } catch (error) {
      setActionError((error as Error).message);
    } finally {
      setUploadPercent(null);
    }
  };

  let description = '';
  if (uploading) {
    description =
      uploadPercent >= 100
        ? 'Đang kiểm tra video...'
        : `Đang tải video lên: ${uploadPercent}%`;
  } else if (cameraStatus === 'starting') {
    description = 'Đang mở camera, hãy cho phép trên trình duyệt nếu được hỏi...';
  } else if (mode === 'browser') {
    description =
      cameraStatus === 'streaming'
        ? 'Đang phân tích hình từ camera laptop. Hãy giữ tab này mở để camera tiếp tục gửi hình.'
        : 'Nguồn đang là camera laptop nhưng chưa có hình gửi lên. Bấm "Camera laptop" để bật lại.';
  } else if (mode === 'video') {
    description = `Đang phát lặp lại video "${status?.uploaded_video ?? ''}" như một camera.`;
  } else if (status) {
    description = `Đang dùng camera đã cấu hình (${status.default_source}).`;
  }

  return (
    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-xs">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <Video className="w-4 h-4 text-sky-500" />
            Nguồn Video Phân Tích
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            {sourceQuery.isError
              ? 'Chưa kết nối được AI Service nên chưa đổi được nguồn video.'
              : description}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={controlsDisabled || mode === 'default'}
            onClick={() => void selectSource('default')}
            className={optionClass(mode === 'default')}
          >
            <Camera className="w-3.5 h-3.5" />
            Camera mặc định
          </button>
          {status?.uploaded_video && (
            <button
              type="button"
              disabled={controlsDisabled || mode === 'video'}
              onClick={() => void selectSource('video')}
              title={status.uploaded_video}
              className={optionClass(mode === 'video')}
            >
              <Video className="w-3.5 h-3.5" />
              Video đã tải
            </button>
          )}
          <button
            type="button"
            disabled={controlsDisabled}
            onClick={() => fileInputRef.current?.click()}
            className={optionClass(false)}
          >
            <Upload className="w-3.5 h-3.5" />
            Tải video lên
          </button>
          <input
            ref={fileInputRef}
            type="file"
            aria-label="Chọn video để phân tích"
            accept=".mp4,.avi,.mkv,.mov,.webm,video/*"
            className="hidden"
            onChange={(event) => void handleFileChosen(event)}
          />
          <button
            type="button"
            disabled={controlsDisabled || (mode === 'browser' && cameraActive)}
            onClick={() => void startLaptopCamera()}
            className={optionClass(mode === 'browser')}
          >
            <Laptop className="w-3.5 h-3.5" />
            Camera laptop
          </button>
        </div>
      </div>

      {!isAuthenticated && (
        <p className="text-xs text-amber-600 dark:text-amber-400 mt-2">
          Hãy đăng nhập bằng tài khoản Operator hoặc Admin để đổi nguồn video.
        </p>
      )}
      {(actionError || cameraError) && (
        <p role="alert" className="text-xs text-rose-600 dark:text-rose-400 mt-2">
          {actionError || cameraError}
        </p>
      )}
      {uploading && (
        <div className="mt-3 h-1.5 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
          <div
            className="h-full bg-sky-500 transition-all"
            style={{ width: `${uploadPercent}%` }}
          />
        </div>
      )}
    </div>
  );
};
