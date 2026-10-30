import React from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { AlertManagementPage } from '../features/alerts/AlertManagementPage';
import { AnalyticsReportsPage } from '../features/analytics/AnalyticsReportsPage';
import { LoginPage } from '../features/auth/LoginPage';
import { DashboardOverviewPage } from '../features/dashboard/DashboardOverviewPage';
import { DensityAnalysisPage } from '../features/density/DensityAnalysisPage';
import { DeviceManagementPage } from '../features/devices/DeviceManagementPage';
import { LiveMonitoringPage } from '../features/monitoring/LiveMonitoringPage';
import { OccupancyManagementPage } from '../features/occupancy/OccupancyManagementPage';
import { RoomZoneManagementPage } from '../features/rooms/RoomZoneManagementPage';
import { SettingsPage } from '../features/settings/SettingsPage';
import { MainLayout } from '../layouts/MainLayout';

export const AppRoutes: React.FC = () => (
  <Routes>
    <Route path="/login" element={<LoginPage />} />

    <Route path="/" element={<MainLayout />}>
      <Route index element={<Navigate to="/dashboard" replace />} />
      <Route path="dashboard" element={<DashboardOverviewPage />} />
      <Route path="monitoring" element={<LiveMonitoringPage />} />
      <Route path="occupancy" element={<OccupancyManagementPage />} />
      <Route path="density" element={<DensityAnalysisPage />} />
      <Route path="rooms" element={<RoomZoneManagementPage />} />
      <Route path="analytics" element={<AnalyticsReportsPage />} />
      <Route path="alerts" element={<AlertManagementPage />} />
      <Route path="devices" element={<DeviceManagementPage />} />
      <Route path="settings" element={<SettingsPage />} />
    </Route>

    <Route path="*" element={<Navigate to="/dashboard" replace />} />
  </Routes>
);
