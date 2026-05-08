"""Bounding box utilities and coordinate conversion."""

import math


def bbox_center(bbox: list[float]) -> tuple[float, float]:
    """Return (cx, cy) center of a normalized bbox [x1, y1, x2, y2]."""
    return (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2


def bbox_to_latlon(
    bbox: list[float],
    footprint: list[float],
) -> tuple[float, float]:
    """Convert a normalized bbox center to geographic coordinates.

    Args:
        bbox: [x1, y1, x2, y2] normalized to [0, 1]
        footprint: [lon_min, lat_min, lon_max, lat_max] from Sentinel metadata

    Returns:
        (latitude, longitude)
    """
    cx, cy = bbox_center(bbox)
    lon_min, lat_min, lon_max, lat_max = footprint

    lon = lon_min + cx * (lon_max - lon_min)
    lat = lat_max - cy * (lat_max - lat_min)

    return lat, lon


def denormalize_bbox(
    bbox: list[float],
    image_width: int,
    image_height: int,
) -> list[int]:
    """Convert normalized [0-1] bbox to pixel coordinates."""
    x1, y1, x2, y2 = bbox
    return [
        int(x1 * image_width),
        int(y1 * image_height),
        int(x2 * image_width),
        int(y2 * image_height),
    ]


def calculate_iou(bbox1: list[float], bbox2: list[float]) -> float:
    """Calculate Intersection over Union of two bboxes."""
    x1 = max(bbox1[0], bbox2[0])
    y1 = max(bbox1[1], bbox2[1])
    x2 = min(bbox1[2], bbox2[2])
    y2 = min(bbox1[3], bbox2[3])

    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    if intersection == 0:
        return 0.0

    area1 = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
    area2 = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
    union = area1 + area2 - intersection

    return intersection / union if union > 0 else 0.0


def non_max_suppression(
    detections: list,
    iou_threshold: float = 0.5,
) -> list:
    """Filter overlapping detections, keeping the highest confidence ones.

    Args:
        detections: list of objects with .bbox and .confidence attributes
        iou_threshold: IoU threshold above which to suppress
    """
    if not detections:
        return []

    sorted_dets = sorted(detections, key=lambda d: d.confidence, reverse=True)
    kept = []

    for det in sorted_dets:
        should_keep = True
        for kept_det in kept:
            if calculate_iou(det.bbox, kept_det.bbox) > iou_threshold:
                should_keep = False
                break
        if should_keep:
            kept.append(det)

    return kept


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two geographic points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
