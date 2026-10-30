import { Point2D } from '../types';

/**
 * Compute the geometric centroid of a polygon in normalized [0..1] space.
 */
export function computePolygonCentroid(points: Point2D[]): Point2D {
  if (!points || points.length === 0) {
    return { x: 0.5, y: 0.5 };
  }
  const sum = points.reduce(
    (acc, pt) => ({ x: acc.x + pt.x, y: acc.y + pt.y }),
    { x: 0, y: 0 },
  );
  return {
    x: Number((sum.x / points.length).toFixed(4)),
    y: Number((sum.y / points.length).toFixed(4)),
  };
}

/**
 * Compute normalized Shoelace polygon area in [0..1] coordinate space.
 */
export function computeNormalizedPolygonArea(points: Point2D[]): number {
  if (!points || points.length < 3) return 0;
  let area = 0;
  for (let i = 0; i < points.length; i += 1) {
    const j = (i + 1) % points.length;
    area += points[i].x * points[j].y;
    area -= points[j].x * points[i].y;
  }
  return Math.abs(area) / 2.0;
}

/**
 * Validate polygon vertices before submitting to FastAPI Backend.
 */
export function validatePolygonCoordinates(points: Point2D[]): string | null {
  if (!points || points.length < 3) {
    return 'Vùng đa giác (Polygon Zone) phải có tối thiểu 3 đỉnh.';
  }
  for (let i = 0; i < points.length; i += 1) {
    const pt = points[i];
    if (
      Number.isNaN(pt.x) ||
      Number.isNaN(pt.y) ||
      pt.x < 0 ||
      pt.x > 1 ||
      pt.y < 0 ||
      pt.y > 1
    ) {
      return `Đỉnh P${i + 1} (${pt.x}, ${pt.y}) nằm ngoài phạm vi chuẩn hóa [0.0, 1.0].`;
    }
  }
  const normArea = computeNormalizedPolygonArea(points);
  if (normArea < 0.001) {
    return 'Diện tích đa giác quá nhỏ hoặc các đỉnh thẳng hàng.';
  }
  return null;
}
