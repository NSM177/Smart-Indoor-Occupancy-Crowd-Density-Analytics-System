/**
 * Singleton that streams the laptop webcam to the AI Service. The AI Service runs
 * in Docker and cannot open the host camera, so the browser captures it and posts
 * JPEG frames one at a time. The next frame is only sent after the previous one was
 * answered, which keeps a slow server from building up a backlog. It lives outside
 * React so the stream survives navigating between pages.
 */

import { create } from 'zustand';
import { useAuthStore } from '../stores/authStore';
import { AI_SERVICE_URL, apiClient } from './axios';

const FRAME_INTERVAL_MS = 100;
const RETRY_INTERVAL_MS = 1_000;
const MAX_FRAME_WIDTH = 960;
const JPEG_QUALITY = 0.75;
const MAX_CONSECUTIVE_FAILURES = 30;

export type BrowserCameraStatus = 'idle' | 'starting' | 'streaming';

interface BrowserCameraState {
  status: BrowserCameraStatus;
  error: string | null;
}

export const useBrowserCameraStore = create<BrowserCameraState>(() => ({
  status: 'idle',
  error: null,
}));

function describeCameraError(error: unknown): string {
  const name = error instanceof DOMException ? error.name : '';
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return 'Trình duyệt chưa được cấp quyền dùng camera. Hãy cho phép camera rồi thử lại.';
  }
  if (name === 'NotFoundError' || name === 'OverconstrainedError') {
    return 'Không tìm thấy camera trên máy này.';
  }
  if (name === 'NotReadableError' || name === 'AbortError') {
    return 'Camera đang được ứng dụng khác sử dụng. Hãy đóng ứng dụng đó rồi thử lại.';
  }
  return 'Không mở được camera trên trình duyệt này.';
}

class BrowserCameraStreamer {
  private stream: MediaStream | null = null;
  private video: HTMLVideoElement | null = null;
  private canvas: HTMLCanvasElement | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private session = 0;
  private failures = 0;
  private tokenRefreshTried = false;

  /** Opens the camera (asks for permission). Returns false if it could not. */
  public async openCamera(): Promise<boolean> {
    this.stop();
    const session = this.session;
    if (!navigator.mediaDevices?.getUserMedia) {
      useBrowserCameraStore.setState({
        status: 'idle',
        error:
          'Trình duyệt chỉ cho phép dùng camera trên HTTPS hoặc localhost. Hãy mở trang bằng http://localhost.',
      });
      return false;
    }

    useBrowserCameraStore.setState({ status: 'starting', error: null });
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      if (session !== this.session) {
        stream.getTracks().forEach((track) => track.stop());
        return false;
      }
      this.stream = stream;
      this.video = document.createElement('video');
      this.video.muted = true;
      this.video.playsInline = true;
      this.video.srcObject = stream;
      await this.video.play();
      this.canvas = document.createElement('canvas');
      return true;
    } catch (error) {
      this.stop();
      useBrowserCameraStore.setState({ error: describeCameraError(error) });
      return false;
    }
  }

  /** Starts sending frames from the camera opened by `openCamera`. */
  public startStreaming(): void {
    if (!this.stream) return;
    this.failures = 0;
    this.tokenRefreshTried = false;
    useBrowserCameraStore.setState({ status: 'streaming', error: null });
    void this.sendNextFrame(this.session);
  }

  public stop(error: string | null = null): void {
    this.session += 1;
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    if (this.video) {
      this.video.srcObject = null;
      this.video = null;
    }
    this.canvas = null;
    useBrowserCameraStore.setState({ status: 'idle', error });
  }

  private captureJpeg(): Promise<Blob | null> {
    const { video, canvas } = this;
    if (!video || !canvas || video.videoWidth === 0) {
      return Promise.resolve(null);
    }
    const scale = Math.min(1, MAX_FRAME_WIDTH / video.videoWidth);
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    canvas.getContext('2d')?.drawImage(video, 0, 0, canvas.width, canvas.height);
    return new Promise((resolve) => {
      canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY);
    });
  }

  private async sendNextFrame(session: number): Promise<void> {
    const startedAt = performance.now();
    let nextDelay = FRAME_INTERVAL_MS;
    try {
      const blob = await this.captureJpeg();
      if (session !== this.session) return;
      if (blob) {
        const response = await fetch(`${AI_SERVICE_URL}/sources/browser/frame`, {
          method: 'POST',
          headers: {
            'Content-Type': 'image/jpeg',
            Authorization: `Bearer ${useAuthStore.getState().accessToken ?? ''}`,
          },
          body: blob,
        });
        if (session !== this.session) return;
        if (response.ok) {
          this.failures = 0;
          this.tokenRefreshTried = false;
        } else if (!(await this.handleRejectedFrame(response.status))) {
          return;
        }
      }
    } catch {
      if (session !== this.session) return;
      this.failures += 1;
      nextDelay = RETRY_INTERVAL_MS;
      if (this.failures >= MAX_CONSECUTIVE_FAILURES) {
        this.stop('Mất kết nối tới AI Service nên đã dừng gửi hình từ camera.');
        return;
      }
    }
    const elapsed = performance.now() - startedAt;
    this.timer = setTimeout(
      () => void this.sendNextFrame(session),
      Math.max(0, nextDelay - elapsed),
    );
  }

  /** Returns true if streaming should continue. */
  private async handleRejectedFrame(status: number): Promise<boolean> {
    if (status === 401 && !this.tokenRefreshTried) {
      // An expired access token is refreshed by the shared axios interceptor
      this.tokenRefreshTried = true;
      try {
        await apiClient.get('/auth/me');
        return true;
      } catch {
        // Falls through to stop below
      }
    }
    if (status === 401 || status === 403) {
      this.stop('Phiên đăng nhập không còn hiệu lực. Hãy đăng nhập lại để dùng camera.');
    } else if (status === 409) {
      this.stop('Nguồn video đã được đổi sang lựa chọn khác nên camera đã dừng.');
    } else {
      this.failures += 1;
      if (this.failures < MAX_CONSECUTIVE_FAILURES) return true;
      this.stop('AI Service liên tục từ chối hình từ camera nên đã dừng gửi.');
    }
    return false;
  }
}

export const browserCamera = new BrowserCameraStreamer();
