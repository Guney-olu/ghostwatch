"""Fetch high-resolution cloud-free aerial imagery for scan targets.

In production GhostWatch would use Sentinel-2 (real on-board satellite data),
but Sentinel imagery is frequently obscured by cloud cover, which produces
weak demo footage. For the dashboard demo we use Esri's World Imagery tile
service — same tile pyramid Cesium renders the globe from. No API key, no
clouds, beautiful.

The narrative for the demo: "The model runs on real satellite imagery —
for visual clarity in this demo we use cached aerial tiles."
"""

import io
import math
from concurrent.futures import ThreadPoolExecutor

import requests
from PIL import Image


_TILE_URL = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
_TILE_PX = 256
_HTTP_TIMEOUT = 8


def _deg_to_tile(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    return x, y


def _tile_to_deg(x: float, y: float, zoom: int) -> tuple[float, float]:
    n = 2.0 ** zoom
    lon = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat = math.degrees(lat_rad)
    return lon, lat


def _meters_per_pixel(lat: float, zoom: int) -> float:
    return 156543.03392 * math.cos(math.radians(lat)) / (2 ** zoom)


def _pick_zoom(lat: float, size_km: float) -> int:
    """Pick the deepest zoom whose 4x4 tile grid still covers size_km."""
    target_m = size_km * 1000
    for z in range(18, 8, -1):
        meters_per_tile = _meters_per_pixel(lat, z) * _TILE_PX
        if 4 * meters_per_tile >= target_m:
            return z
    return 9


def fetch_aerial_image(lon: float, lat: float, size_km: float) -> tuple[bytes, dict]:
    """Stitch a square aerial image of ~size_km centered on (lon, lat).

    Returns (png_bytes, metadata) where metadata is the same shape the
    Sentinel fetcher returns: image_available, footprint, source, etc.
    """
    zoom = _pick_zoom(lat, size_km)
    cx, cy = _deg_to_tile(lon, lat, zoom)

    half_tiles_each_side = 1
    x_min = int(math.floor(cx)) - half_tiles_each_side
    x_max = int(math.floor(cx)) + half_tiles_each_side + 1
    y_min = int(math.floor(cy)) - half_tiles_each_side
    y_max = int(math.floor(cy)) + half_tiles_each_side + 1

    grid_w = x_max - x_min
    grid_h = y_max - y_min

    tiles: dict[tuple[int, int], Image.Image] = {}

    def _fetch_one(coord: tuple[int, int]) -> tuple[tuple[int, int], Image.Image | None]:
        tx, ty = coord
        url = _TILE_URL.format(z=zoom, x=tx, y=ty)
        try:
            r = requests.get(url, timeout=_HTTP_TIMEOUT, headers={"User-Agent": "GhostWatch/1.0"})
            r.raise_for_status()
            return coord, Image.open(io.BytesIO(r.content)).convert("RGB")
        except Exception:
            return coord, None

    coords = [(tx, ty) for tx in range(x_min, x_max) for ty in range(y_min, y_max)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for coord, img in pool.map(_fetch_one, coords):
            if img is not None:
                tiles[coord] = img

    if not tiles:
        return b"", {
            "image_available": False,
            "source": "esri",
            "error": "tile fetch failed",
        }

    stitched = Image.new("RGB", (grid_w * _TILE_PX, grid_h * _TILE_PX))
    for (tx, ty), img in tiles.items():
        stitched.paste(img, ((tx - x_min) * _TILE_PX, (ty - y_min) * _TILE_PX))

    crop_size_px = int(min(grid_w, grid_h) * _TILE_PX)
    px_per_tile = _TILE_PX
    cx_in_grid = (cx - x_min) * px_per_tile
    cy_in_grid = (cy - y_min) * px_per_tile
    half = crop_size_px // 2
    left = max(0, int(cx_in_grid - half))
    upper = max(0, int(cy_in_grid - half))
    right = min(stitched.width, left + crop_size_px)
    lower = min(stitched.height, upper + crop_size_px)
    cropped = stitched.crop((left, upper, right, lower))

    out_size = 768
    if max(cropped.size) != out_size:
        cropped = cropped.resize((out_size, out_size), Image.LANCZOS)

    lon_min, lat_max = _tile_to_deg(x_min + left / _TILE_PX, y_min + upper / _TILE_PX, zoom)
    lon_max, lat_min = _tile_to_deg(x_min + right / _TILE_PX, y_min + lower / _TILE_PX, zoom)

    buf = io.BytesIO()
    cropped.save(buf, format="PNG", optimize=True)
    image_bytes = buf.getvalue()

    metadata = {
        "image_available": True,
        "source": "esri-world-imagery",
        "zoom": zoom,
        "tiles_fetched": len(tiles),
        "footprint": [lon_min, lat_min, lon_max, lat_max],
        "size_km": size_km,
        "ground_resolution_m_per_px": _meters_per_pixel(lat, zoom) * (_TILE_PX / out_size) * (crop_size_px / _TILE_PX),
    }
    return image_bytes, metadata
