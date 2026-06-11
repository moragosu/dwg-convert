"""
Y축 밀도 분석으로 생산 라인 레이아웃 존 자동 감지.

알고리즘:
  1. LINE 엔티티의 Y좌표 수집
  2. Y 히스토그램 → Gaussian 스무딩
  3. 저밀도 구간(갭) 감지 → 존 경계
  4. 각 존의 실제 엔티티 XY 좌표로 convex hull / concave hull 생성
"""
import re
import numpy as np
from typing import Optional
from shapely.geometry import Polygon, MultiPoint
from ezdxf.document import Drawing

ZONE_COLORS = ["#0066FF", "#FF6600", "#00AA44", "#CC0055", "#AAAA00", "#00AACC",
               "#8833CC", "#CC8800", "#0099AA", "#CC3333"]

MAX_SAMPLE = 300_000  # Y 수집 샘플 상한
MARGIN_MM = 2_000     # 존 경계 여유 (2m)


def find_layout_zones(
    doc: Drawing,
    min_gap_mm: float = 1500,
    min_zone_height_mm: float = 3000,
    min_entities: int = 30,
) -> list[tuple[str, Polygon]]:
    """
    DXF 문서에서 생산 라인 존을 자동 감지.

    Returns:
        [(zone_name, shapely_polygon), ...]  Y좌표 오름차순
    """
    msp = doc.modelspace()

    # ── 1단계: Y좌표 수집 ──────────────────────────────────────────
    ys_all: list[float] = []
    entity_pts: list[tuple[float, float]] = []
    count = 0
    for e in msp:
        if count >= MAX_SAMPLE:
            break
        try:
            if e.dxftype() == "LINE":
                y = e.dxf.start.y
                ys_all.append(y)
                entity_pts.append((e.dxf.start.x, y))
                entity_pts.append((e.dxf.end.x, e.dxf.end.y))
                count += 1
            elif e.dxftype() == "LWPOLYLINE":
                for p in e.get_points():
                    ys_all.append(p[1])
                    entity_pts.append((p[0], p[1]))
                count += 1
        except Exception:
            pass

    if not ys_all:
        raise RuntimeError("도면에서 엔티티를 찾을 수 없습니다.")

    ys = np.array(ys_all)
    y_min, y_max = float(ys.min()), float(ys.max())
    y_range = y_max - y_min

    if y_range < min_zone_height_mm * 2:
        raise RuntimeError(
            f"Y 범위({y_range/1000:.1f}m)가 너무 작아 존 감지 불가."
        )

    # ── 2단계: Y 히스토그램 + 스무딩 ─────────────────────────────
    n_bins = 600
    hist, edges = np.histogram(ys, bins=n_bins, range=(y_min, y_max))
    bin_width = (y_max - y_min) / n_bins  # mm/bin

    # Gaussian 스무딩 (sigma ≈ 2m / bin_width bins)
    sigma_bins = max(1, int(2000 / bin_width))
    kernel_half = sigma_bins * 3
    kernel_x = np.arange(-kernel_half, kernel_half + 1)
    kernel = np.exp(-0.5 * (kernel_x / sigma_bins) ** 2)
    kernel /= kernel.sum()
    smooth = np.convolve(hist.astype(float), kernel, mode="same")

    # ── 3단계: 갭(저밀도 구간) 감지 ──────────────────────────────
    threshold = smooth.mean() * 0.15  # 평균의 15% 미만 = 갭
    is_gap = smooth < threshold

    # 연속된 갭 구간을 하나로 병합
    gap_regions: list[tuple[float, float]] = []
    in_gap = False
    gap_start_bin = 0
    for i, g in enumerate(is_gap):
        if g and not in_gap:
            in_gap = True
            gap_start_bin = i
        elif not g and in_gap:
            in_gap = False
            g_y_start = edges[gap_start_bin]
            g_y_end = edges[i]
            if (g_y_end - g_y_start) >= min_gap_mm:
                gap_regions.append((g_y_start, g_y_end))
    if in_gap:
        g_y_start = edges[gap_start_bin]
        g_y_end = edges[-1]
        if (g_y_end - g_y_start) >= min_gap_mm:
            gap_regions.append((g_y_start, g_y_end))

    # ── 4단계: 존 경계 결정 ───────────────────────────────────────
    zone_boundaries: list[tuple[float, float]] = []
    prev_end = y_min
    for g_start, g_end in sorted(gap_regions, key=lambda x: x[0]):
        zone_boundaries.append((prev_end, g_start))
        prev_end = g_end
    zone_boundaries.append((prev_end, y_max))

    # ── 5단계: 각 존의 공간 범위 및 폴리곤 생성 ──────────────────
    pts_array = np.array(entity_pts)
    pt_xs = pts_array[:, 0]
    pt_ys = pts_array[:, 1]

    zones: list[tuple[str, Polygon]] = []
    for band_y_min, band_y_max in zone_boundaries:
        mask = (pt_ys >= band_y_min) & (pt_ys <= band_y_max)
        n_pts = int(mask.sum())
        if n_pts < min_entities:
            continue
        if (band_y_max - band_y_min) < min_zone_height_mm:
            continue

        bx = pt_xs[mask]
        by = pt_ys[mask]
        x_lo = float(bx.min()) - MARGIN_MM
        x_hi = float(bx.max()) + MARGIN_MM
        y_lo = band_y_min - MARGIN_MM
        y_hi = band_y_max + MARGIN_MM

        poly = _zone_polygon(bx, by, x_lo, x_hi, y_lo, y_hi)
        if poly is None or not poly.is_valid or poly.area < 1e6:
            # 폴백: 직사각형 경계
            poly = Polygon([
                (x_lo, y_lo), (x_hi, y_lo),
                (x_hi, y_hi), (x_lo, y_hi),
            ])

        zones.append((f"LINE_{len(zones)+1}", poly))

    if not zones:
        raise RuntimeError(
            "라인 존을 감지하지 못했습니다.\n"
            "min_gap_mm 값을 줄이거나 도면 구조를 확인하세요."
        )

    # Y 오름차순 정렬 (Y가 음수이므로 centroid.y 기준 내림차순 = 화면 위→아래)
    zones.sort(key=lambda z: z[1].centroid.y, reverse=True)
    return [(f"LINE_{i+1}", poly) for i, (_, poly) in enumerate(zones)]


def _zone_polygon(
    bx: np.ndarray,
    by: np.ndarray,
    x_lo: float, x_hi: float,
    y_lo: float, y_hi: float,
) -> Optional[Polygon]:
    """존 내 포인트 샘플로 concave hull 또는 convex hull 생성."""
    try:
        # 너무 많으면 서브샘플링
        n = len(bx)
        if n > 5000:
            idx = np.random.choice(n, 5000, replace=False)
            bx, by = bx[idx], by[idx]

        mp = MultiPoint(list(zip(bx.tolist(), by.tolist())))

        # shapely 2.0+: concave_hull 지원
        try:
            from shapely import concave_hull
            poly = concave_hull(mp, ratio=0.2)
            if poly.is_valid and poly.area > 1e6:
                return poly
        except (ImportError, AttributeError, Exception):
            pass

        # 폴백: convex hull
        return mp.convex_hull if mp.convex_hull.geom_type == "Polygon" else None

    except Exception:
        return None


def zone_summary(zones: list[tuple[str, Polygon]]) -> str:
    """존 목록 요약 문자열 (UI 표시용)."""
    lines = []
    for name, poly in zones:
        b = poly.bounds
        w = (b[2] - b[0]) / 1000
        h = (b[3] - b[1]) / 1000
        lines.append(f"{name}: {w:.1f}m × {h:.1f}m  ({poly.area/1e6:.0f}m²)")
    return "\n".join(lines)


def extract_hull_in_region(
    doc,
    x0: float, y0: float,
    x1: float, y1: float,
    min_entities: int = 10,
) -> Optional[Polygon]:
    """
    사용자가 지정한 직사각형 영역(x0,y0)~(x1,y1) 내부의
    엔티티 좌표로 concave/convex hull 폴리곤 생성.
    엔티티가 min_entities 미만이면 None 반환.
    """
    msp = doc.modelspace()
    xs: list[float] = []
    ys: list[float] = []

    for e in msp:
        try:
            if e.dxftype() == "LINE":
                for pt in (e.dxf.start, e.dxf.end):
                    if x0 <= pt.x <= x1 and y0 <= pt.y <= y1:
                        xs.append(pt.x)
                        ys.append(pt.y)
            elif e.dxftype() == "LWPOLYLINE":
                for p in e.get_points():
                    if x0 <= p[0] <= x1 and y0 <= p[1] <= y1:
                        xs.append(p[0])
                        ys.append(p[1])
        except Exception:
            pass

    if len(xs) < min_entities:
        return None

    bx = np.array(xs)
    by = np.array(ys)
    poly = _zone_polygon(bx, by, x0, x1, y0, y1)
    if poly is None or not poly.is_valid or poly.area < 1e6:
        poly = Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
    return poly
