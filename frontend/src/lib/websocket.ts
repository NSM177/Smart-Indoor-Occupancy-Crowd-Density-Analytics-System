/**
 * Singleton Native WebSocket Manager for `/ws/realtime`.
 * Prevents duplicate connections across React components, handles exponential
 * backoff auto-reconnect, sends periodic `ping` heartbeats, updates Zustand
 * realtime state, and invalidates TanStack Query caches on new events.
 */

import { WS_URL } from './axios';
import { queryClient } from './queryClient';
import { useRealtimeStore } from '../stores/realtimeStore';
import { AlertEntity, WsEnvelope } from '../types';

class RealtimeWebSocketSingleton {
  private socket: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private staleCheckTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectAttempts = 0;
  private activeRoomId = 'room1';
  private isIntentionalClose = false;
  private subscriberCount = 0;

  public acquire(roomId: string): void {
    this.subscriberCount += 1;
    if (roomId && roomId !== this.activeRoomId) {
      this.activeRoomId = roomId;
      this.subscribeRoom(roomId);
    }
    if (!this.socket || this.socket.readyState === WebSocket.CLOSED) {
      this.isIntentionalClose = false;
      this.connect();
    }
    this.startStaleMonitor();
  }

  public release(): void {
    this.subscriberCount = Math.max(0, this.subscriberCount - 1);
    if (this.subscriberCount === 0) {
      this.disconnect();
    }
  }

  public switchRoom(roomId: string): void {
    if (!roomId || roomId === this.activeRoomId) return;
    this.activeRoomId = roomId;
    this.subscribeRoom(roomId);
  }

  private connect(): void {
    if (
      this.socket &&
      (this.socket.readyState === WebSocket.OPEN ||
        this.socket.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    const store = useRealtimeStore.getState();
    store.setConnectionStatus(
      this.reconnectAttempts > 0 ? 'RECONNECTING' : 'CONNECTING',
    );

    const url = `${WS_URL}?room_id=${encodeURIComponent(this.activeRoomId)}`;
    try {
      this.socket = new WebSocket(url);
    } catch {
      this.scheduleReconnect();
      return;
    }

    this.socket.onopen = () => {
      this.reconnectAttempts = 0;
      useRealtimeStore.getState().setConnectionStatus('CONNECTED');
      this.subscribeRoom(this.activeRoomId);
      this.startHeartbeat();
    };

    this.socket.onmessage = (event: MessageEvent) => {
      try {
        const envelope = JSON.parse(String(event.data)) as WsEnvelope;
        this.handleEnvelope(envelope);
      } catch {
        // Ignore malformed frame
      }
    };

    this.socket.onerror = () => {
      // Handled in onclose
    };

    this.socket.onclose = () => {
      this.stopHeartbeat();
      useRealtimeStore.getState().setConnectionStatus('DISCONNECTED');
      if (!this.isIntentionalClose && this.subscriberCount > 0) {
        this.scheduleReconnect();
      }
    };
  }

  private handleEnvelope(envelope: WsEnvelope): void {
    const store = useRealtimeStore.getState();
    const roomKey = envelope.room_id || this.activeRoomId;

    if (envelope.event === 'connected' && envelope.initial_state) {
      store.updateRoomOccupancy(
        roomKey,
        envelope.initial_state as Record<string, unknown>,
      );
      return;
    }

    if (envelope.event === 'occupancy.updated' && envelope.data) {
      store.updateRoomOccupancy(roomKey, envelope.data);
      queryClient.invalidateQueries({ queryKey: ['occupancy-current'] });
      return;
    }

    if (envelope.event === 'density.updated' && envelope.data) {
      store.updateRoomOccupancy(roomKey, envelope.data);
      queryClient.invalidateQueries({ queryKey: ['density-current'] });
      return;
    }

    if (envelope.event === 'zone.updated' && envelope.data) {
      const zones = (envelope.data as { zones?: unknown[] }).zones;
      if (Array.isArray(zones)) {
        store.updateRoomOccupancy(roomKey, {
          zones: zones as never,
        });
      }
      queryClient.invalidateQueries({ queryKey: ['density-current'] });
      return;
    }

    if (envelope.event === 'alert.created' && envelope.data) {
      const alertObj = envelope.data as unknown as AlertEntity;
      store.pushLiveAlert(alertObj);
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
      return;
    }

    if (envelope.event === 'device.status_changed') {
      queryClient.invalidateQueries({ queryKey: ['devices'] });
    }
  }

  private subscribeRoom(roomId: string): void {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(
        JSON.stringify({
          type: 'subscribeRoom',
          roomId,
        }),
      );
    }
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.socket && this.socket.readyState === WebSocket.OPEN) {
        this.socket.send(JSON.stringify({ type: 'ping' }));
      }
    }, 20_000);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private startStaleMonitor(): void {
    if (this.staleCheckTimer) return;
    this.staleCheckTimer = setInterval(() => {
      useRealtimeStore.getState().checkStale(30_000);
    }, 5_000);
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    this.reconnectAttempts += 1;
    const delayMs = Math.min(15_000, 1_000 * 2 ** Math.min(this.reconnectAttempts, 4));
    useRealtimeStore.getState().setConnectionStatus('RECONNECTING');
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delayMs);
  }

  private disconnect(): void {
    this.isIntentionalClose = true;
    this.stopHeartbeat();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.staleCheckTimer) {
      clearInterval(this.staleCheckTimer);
      this.staleCheckTimer = null;
    }
    if (this.socket) {
      try {
        this.socket.close();
      } catch {
        // Ignore
      }
      this.socket = null;
    }
    useRealtimeStore.getState().setConnectionStatus('DISCONNECTED');
  }
}

export const wsClientSingleton = new RealtimeWebSocketSingleton();
