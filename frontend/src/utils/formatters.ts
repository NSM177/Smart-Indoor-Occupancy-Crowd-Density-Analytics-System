/**
 * Formatting & CSV Export Utilities.
 */

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return 'Chưa ghi nhận';
  try {
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return iso;
    return dt.toLocaleString('vi-VN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  } catch {
    return iso;
  }
}

export function formatTimeShort(iso: string | null | undefined): string {
  if (!iso) return '--:--:--';
  try {
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return iso;
    return dt.toLocaleTimeString('vi-VN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return iso;
  }
}

export function formatDensity(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '0.00';
  }
  return value.toFixed(2);
}

export function formatPercentage(ratioOrPct: number, isRatio = false): string {
  const pct = isRatio ? ratioOrPct * 100 : ratioOrPct;
  return `${Math.min(999, Math.max(0, pct)).toFixed(1)}%`;
}

export function exportToCsv(
  filename: string,
  headers: string[],
  rows: Array<Array<string | number | boolean | null | undefined>>,
): void {
  const escapeCell = (val: string | number | boolean | null | undefined): string => {
    if (val === null || val === undefined) return '';
    const str = String(val).replace(/"/g, '""');
    return /[,"\n]/.test(str) ? `"${str}"` : str;
  };

  const csvContent = [
    headers.map(escapeCell).join(','),
    ...rows.map((row) => row.map(escapeCell).join(',')),
  ].join('\n');

  const blob = new Blob([`\uFEFF${csvContent}`], {
    type: 'text/csv;charset=utf-8;',
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
