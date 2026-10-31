import React from 'react';
import { act, render, renderHook, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { StatCard } from '../components/dashboard/StatCard';
import { InteractiveFloorPlan } from '../components/monitoring/SpatialWidgets';
import { SectionCard, StatusBadge } from '../components/ui/Primitives';
import { SIDEBAR_NAV_ITEMS } from '../layouts/MainLayout';
import { useAuthStore } from '../stores/authStore';
import { useLiveRoomMetrics, useRealtimeStore } from '../stores/realtimeStore';
import { useUIStore } from '../stores/uiStore';
import {
  computeNormalizedPolygonArea,
  computePolygonCentroid,
  validatePolygonCoordinates,
} from '../utils/polygon';

describe('1. Polygon Geometry & Validation Utilities', () => {
  it('validates polygon vertices and rejects fewer than 3 vertices or out-of-range coordinates', () => {
    expect(
      validatePolygonCoordinates([
        { x: 0.1, y: 0.1 },
        { x: 0.5, y: 0.1 },
      ]),
    ).toContain('tối thiểu 3 đỉnh');

    expect(
      validatePolygonCoordinates([
        { x: -0.1, y: 0.1 },
        { x: 0.5, y: 0.1 },
        { x: 0.5, y: 0.5 },
      ]),
    ).toContain('nằm ngoài phạm vi');

    expect(
      validatePolygonCoordinates([
        { x: 0.1, y: 0.1 },
        { x: 0.5, y: 0.1 },
        { x: 0.5, y: 0.5 },
        { x: 0.1, y: 0.5 },
      ]),
    ).toBeNull();
  });

  it('computes accurate polygon centroid and normalized area', () => {
    const square = [
      { x: 0.0, y: 0.0 },
      { x: 0.5, y: 0.0 },
      { x: 0.5, y: 0.5 },
      { x: 0.0, y: 0.5 },
    ];
    expect(computePolygonCentroid(square)).toEqual({ x: 0.25, y: 0.25 });
    expect(computeNormalizedPolygonArea(square)).toBeCloseTo(0.25, 4);
  });
});

describe('2. Zustand Stores (Auth, UI Theme, Realtime Telemetry & Stale Data)', () => {
  it('manages JWT session state in useAuthStore', () => {
    const store = useAuthStore.getState();
    store.setSession('access_tok_123', 'refresh_tok_456', {
      id: 'u1',
      username: 'admin',
      email: 'admin@occupancy.local',
      full_name: 'Admin User',
      role: 'ADMIN',
      is_active: true,
      created_at: new Date().toISOString(),
    });
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(useAuthStore.getState().user?.role).toBe('ADMIN');

    store.clearSession();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it('toggles Light/Dark theme and updates selected room in useUIStore', () => {
    const ui = useUIStore.getState();
    ui.setTheme('light');
    expect(useUIStore.getState().theme).toBe('light');
    expect(document.documentElement.classList.contains('dark')).toBe(false);

    ui.toggleTheme();
    expect(useUIStore.getState().theme).toBe('dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);

    ui.setSelectedRoomId('lab_202');
    expect(useUIStore.getState().selectedRoomId).toBe('lab_202');
  });

  it('updates realtime room occupancy, alerts, and detects stale data in useRealtimeStore', () => {
    const rt = useRealtimeStore.getState();
    rt.updateRoomOccupancy('room1', {
      room_id: 'room1',
      room_code: 'room1',
      current_count: 42,
      in_count: 50,
      out_count: 8,
      overall_density: 0.35,
      capacity_ratio: 0.7,
      room_status: 'WARNING',
    });

    expect(useRealtimeStore.getState().liveRooms.room1.current_count).toBe(42);
    expect(useRealtimeStore.getState().isStale).toBe(false);

    rt.pushLiveAlert({
      id: 'alert_99',
      room_id: 'room1',
      zone_id: null,
      alert_type: 'CROWD_DENSITY_THRESHOLD',
      severity: 'CRITICAL',
      message: 'Room 1 overcrowded',
      person_count: 65,
      density_value: 0.85,
      threshold_value: 0.8,
      is_acknowledged: false,
      acknowledged_by: null,
      acknowledged_at: null,
      is_resolved: false,
      resolved_at: null,
      triggered_at: new Date().toISOString(),
    });

    expect(useRealtimeStore.getState().unreadAlertCount).toBeGreaterThanOrEqual(1);
    rt.markAlertsRead();
    expect(useRealtimeStore.getState().unreadAlertCount).toBe(0);
  });
});

describe('3. UI & Spatial Monitoring Components', () => {
  it('verifies all 9 required Sidebar Navigation routes exist', () => {
    expect(SIDEBAR_NAV_ITEMS).toHaveLength(9);
    const labels = SIDEBAR_NAV_ITEMS.map((i) => i.label);
    expect(labels).toEqual([
      'Dashboard',
      'Live Monitoring',
      'Occupancy Management',
      'Density Analysis',
      'Room & Zone Management',
      'Analytics & Reports',
      'Alert Management',
      'Device Management',
      'Settings',
    ]);
  });

  it('renders StatCard, StatusBadge, SectionCard, and InteractiveFloorPlan', () => {
    render(
      <div>
        <StatCard
          label="Total People"
          value={38}
          subValue="In: 45 • Out: 7"
          icon={<span>ICON</span>}
        />
        <StatusBadge status="CRITICAL" />
        <SectionCard title="Density Map">
          <InteractiveFloorPlan
            zones={[
              {
                id: 'z1',
                room_id: 'r1',
                name: 'Zone A',
                code: 'ZONE_A',
                polygon_coordinates: [
                  { x: 0.1, y: 0.1 },
                  { x: 0.4, y: 0.1 },
                  { x: 0.4, y: 0.8 },
                  { x: 0.1, y: 0.8 },
                ],
                area_sqm: 36,
                max_capacity: 18,
                warning_density: 0.5,
                critical_density: 0.8,
                color_hex: '#3B82F6',
                created_at: '',
                updated_at: '',
              },
            ]}
            zoneMetrics={[
              {
                zone_id: 'z1',
                zone_code: 'ZONE_A',
                zone_name: 'Zone A',
                person_count: 16,
                area_sqm: 36,
                max_capacity: 18,
                density_per_sqm: 0.4444,
                capacity_ratio: 0.8889,
                utilization_pct: 88.9,
                severity: 'WARNING',
              },
            ]}
          />
        </SectionCard>
      </div>,
    );

    expect(screen.getByText('Total People')).toBeInTheDocument();
    expect(screen.getByText('38')).toBeInTheDocument();
    expect(screen.getByText('CRITICAL')).toBeInTheDocument();
    expect(screen.getByText(/ZONE_A • 16\/18 người/i)).toBeInTheDocument();
  });
});

describe('Realtime rendering performance (Phase 1)', () => {
  it('useLiveRoomMetrics re-renders only when a displayed KPI changes', () => {
    useRealtimeStore.setState({ liveRooms: {} });
    let renders = 0;
    const { result } = renderHook(() => {
      renders += 1;
      return useLiveRoomMetrics('room_perf');
    });
    expect(result.current).toBeNull();

    const frame = {
      room_id: 'room_perf',
      room_code: 'room_perf',
      current_count: 12,
      in_count: 20,
      out_count: 8,
      overall_density: 0.1,
      capacity_ratio: 0.2,
      room_status: 'NORMAL' as const,
    };
    act(() => useRealtimeStore.getState().updateRoomOccupancy('room_perf', frame));
    expect(result.current?.current_count).toBe(12);
    const rendersAfterFirstFrame = renders;

    // Same KPIs again (new object, new zones/updated_at) -> no re-render
    act(() =>
      useRealtimeStore.getState().updateRoomOccupancy('room_perf', {
        ...frame,
        zones: [],
        updated_at: new Date().toISOString(),
      }),
    );
    expect(renders).toBe(rendersAfterFirstFrame);

    act(() =>
      useRealtimeStore
        .getState()
        .updateRoomOccupancy('room_perf', { ...frame, current_count: 13 }),
    );
    expect(renders).toBe(rendersAfterFirstFrame + 1);
    expect(result.current?.current_count).toBe(13);
  });

  it('stores streamed heatmaps under every room key and renders them on a canvas', () => {
    const grid = [
      [0.0, 0.5],
      [0.9, 0.2],
    ];
    useRealtimeStore.getState().updateHeatmap(['uuid-1', 'room1', ''], grid);
    const heatmaps = useRealtimeStore.getState().liveHeatmaps;
    expect(heatmaps['uuid-1']).toBe(grid);
    expect(heatmaps.room1).toBe(grid);
    expect(heatmaps['']).toBeUndefined();

    const { container } = render(
      <InteractiveFloorPlan zones={[]} zoneMetrics={[]} heatmapGrid={grid} />,
    );
    const canvas = container.querySelector('canvas');
    expect(canvas).not.toBeNull();
    expect(canvas?.getAttribute('width')).toBe('2');
    expect(canvas?.getAttribute('height')).toBe('2');
  });
});
