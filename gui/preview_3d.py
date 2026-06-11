"""
3D 미리보기.
render_3d_axes() : 순수 matplotlib 렌더링 (GUI 없이 호출 가능)
show_3d_preview(): tkinter Toplevel 창으로 표시
"""
from __future__ import annotations
from typing import Optional

import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from shapely.geometry import Polygon

_COLORS_3D = [
    (0.2, 0.4, 1.0),
    (1.0, 0.45, 0.1),
    (0.1, 0.8, 0.35),
    (0.8, 0.0, 0.35),
    (0.65, 0.65, 0.0),
    (0.0, 0.65, 0.8),
    (0.55, 0.2, 0.8),
    (0.8, 0.55, 0.0),
]
_MAX_VERTS = 200   # 존당 꼭짓점 상한 (3D 성능)


# ── 공용 렌더링 함수 ──────────────────────────────────────────────────────────

def render_3d_axes(
    ax,
    zones: list[tuple[str, Polygon]],
    height_mm: float,
) -> None:
    """주어진 3D axes에 압출 솔리드를 그린다."""
    ax.clear()
    ax.set_facecolor("#1a1a2e")

    all_bounds = [poly.bounds for _, poly in zones]
    ox = min(b[0] for b in all_bounds)
    oy = min(b[1] for b in all_bounds)
    h_m = height_mm / 1000.0

    all_xs: list[float] = []
    all_ys: list[float] = []

    for i, (name, poly) in enumerate(zones):
        color = _COLORS_3D[i % len(_COLORS_3D)]
        coords = _to_meters(poly, _MAX_VERTS, ox, oy)
        if len(coords) < 3:
            continue

        faces = _extrude_faces(coords, h_m)
        col = Poly3DCollection(faces, zsort="min")
        col.set_facecolor((*color, 0.28))
        col.set_edgecolor((*color, 0.85))
        col.set_linewidth(0.4)
        ax.add_collection3d(col)

        cx = float(np.mean([v[0] for v in coords]))
        cy = float(np.mean([v[1] for v in coords]))
        ax.text(cx, cy, h_m * 1.08, name,
                color=[min(c * 1.4, 1.0) for c in color],
                fontsize=10, fontweight="bold", ha="center")

        all_xs += [v[0] for v in coords]
        all_ys += [v[1] for v in coords]

    if all_xs:
        px = (max(all_xs) - min(all_xs)) * 0.03
        py = (max(all_ys) - min(all_ys)) * 0.03
        ax.set_xlim(min(all_xs) - px, max(all_xs) + px)
        ax.set_ylim(min(all_ys) - py, max(all_ys) + py)
        ax.set_zlim(0, h_m * 1.4)

    ax.set_xlabel("X (m)", color="#8888aa", fontsize=9, labelpad=6)
    ax.set_ylabel("Y (m)", color="#8888aa", fontsize=9, labelpad=6)
    ax.set_zlabel("Z (m)", color="#8888aa", fontsize=9, labelpad=6)
    ax.tick_params(colors="#666688", labelsize=7)
    for pane in (ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane):
        pane.fill = False
        pane.set_edgecolor("#2a2a4a")
    ax.grid(True, color="#2a2a4a", linewidth=0.5)
    ax.set_title(
        f"3D Preview  —  {len(zones)} zone(s)  @  {height_mm:.0f} mm",
        color="white", fontsize=11, fontweight="bold", pad=8,
    )
    ax.view_init(elev=25, azim=-60)


# ── tkinter 미리보기 창 ──────────────────────────────────────────────────────

def show_3d_preview(
    zones: list[tuple[str, Polygon]],
    height_mm: float,
    parent=None,
) -> None:
    """tkinter Toplevel 3D 미리보기 창을 연다."""
    if not zones:
        return
    import matplotlib
    matplotlib.use("TkAgg")
    import tkinter as tk
    from tkinter import ttk
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

    win = tk.Toplevel(parent)
    win.title("3D 미리보기")
    win.geometry("1000x720")
    win.resizable(True, True)

    # ── 상단 컨트롤 바 ──
    top = ttk.Frame(win, padding=(6, 4))
    top.pack(fill="x")

    ttk.Label(top, text="높이(mm):").pack(side="left")
    height_var = tk.StringVar(value=str(int(height_mm)))
    ttk.Entry(top, textvariable=height_var, width=8).pack(side="left", padx=(2, 8))

    fig = plt.figure(figsize=(12, 8), facecolor="#12121f")
    ax = fig.add_subplot(111, projection="3d")

    def do_render():
        try:
            h = float(height_var.get())
        except ValueError:
            return
        render_3d_axes(ax, zones, h)
        canvas.draw()

    ttk.Button(top, text="업데이트", command=do_render).pack(side="left", padx=(0, 12))

    ttk.Label(top, text="시점:").pack(side="left")
    for label, elev, azim in [("정면", 5, -90), ("측면", 5, 0), ("위", 85, -90), ("사선", 25, -60)]:
        def _view(e=elev, a=azim):
            ax.view_init(elev=e, azim=a)
            canvas.draw()
        ttk.Button(top, text=label, width=5, command=_view).pack(side="left", padx=2)

    # ── matplotlib 캔버스 임베드 ──
    canvas = FigureCanvasTkAgg(fig, master=win)
    canvas.get_tk_widget().pack(fill="both", expand=True)

    toolbar_frm = ttk.Frame(win)
    toolbar_frm.pack(fill="x")
    NavigationToolbar2Tk(canvas, toolbar_frm)

    render_3d_axes(ax, zones, height_mm)
    canvas.draw()
    win.focus_set()


# ── 내부 헬퍼 ────────────────────────────────────────────────────────────────

def _to_meters(
    poly: Polygon,
    max_verts: int,
    ox: float,
    oy: float,
) -> list[tuple[float, float]]:
    coords = list(poly.exterior.coords[:-1])
    if len(coords) > max_verts:
        idx = np.round(np.linspace(0, len(coords) - 1, max_verts)).astype(int)
        coords = [coords[i] for i in idx]
    return [((x - ox) / 1000.0, (y - oy) / 1000.0) for x, y in coords]


def _extrude_faces(
    coords: list[tuple[float, float]],
    h: float,
) -> list[list[tuple[float, float, float]]]:
    n = len(coords)
    faces: list[list[tuple[float, float, float]]] = []
    faces.append([(x, y, 0.0) for x, y in coords])
    faces.append([(x, y, h) for x, y in coords])
    for i in range(n):
        x0, y0 = coords[i]
        x1, y1 = coords[(i + 1) % n]
        faces.append([(x0, y0, 0.0), (x1, y1, 0.0), (x1, y1, h), (x0, y0, h)])
    return faces
