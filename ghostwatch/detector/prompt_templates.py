"""Prompt templates for vessel detection with Liquid AI VLMs."""

import json
import re
from dataclasses import dataclass


@dataclass
class Detection:
    label: str
    confidence: float
    bbox: list[float]


FINETUNED_PROMPT = (
    "Detect all ships and vessels in this satellite image. "
    "Return a JSON array where each element has "
    '"label" and "bbox" [x1, y1, x2, y2] normalized to [0, 1].'
)


GROUNDING_PROMPT = (
    "Detect all ships, boats, and vessels visible in this satellite image. "
    "For each object found, return a JSON array where each element has: "
    '"label" (one of: cargo_ship, tanker, fishing_boat, patrol_vessel, sailboat, unknown_vessel), '
    '"confidence" (0.0 to 1.0), and '
    '"bbox" [x1, y1, x2, y2] with coordinates normalized to [0, 1]. '
    "If no vessels are visible, return an empty array []."
)

MARITIME_ANALYSIS_PROMPT = (
    "You are analyzing a 10-meter resolution Sentinel-2 satellite image of a maritime region. "
    "Ships appear as small bright objects against dark water. "
    "Identify all vessels visible in this image. For each vessel, provide: "
    '"label" (cargo_ship, tanker, fishing_boat, patrol_vessel, sailboat, or unknown_vessel), '
    '"confidence" (0.0 to 1.0), '
    '"bbox" [x1, y1, x2, y2] normalized to [0, 1], and '
    '"estimated_size" (small, medium, large). '
    "Return as a JSON array. If no vessels are visible, return []."
)

SCENE_DESCRIPTION_PROMPT = (
    "Analyze this satellite image for maritime vessels. "
    "For each ship, boat, or vessel you can see, state: "
    "1) The vessel type (cargo ship, tanker, fishing boat, etc.) "
    "2) Its position in the image using one of: upper-left, upper-center, upper-right, "
    "center-left, center, center-right, lower-left, lower-center, lower-right "
    "3) Its estimated size: small, medium, or large. "
    "Format each vessel on its own line like: 'VESSEL: <type>, <position>, <size>'. "
    "If no vessels are visible, write: 'NO VESSELS DETECTED'."
)


def parse_detection_response(raw_text: str) -> list[Detection]:
    """Parse VLM output into structured detections.

    Handles: valid JSON arrays, malformed JSON, or free-text descriptions.
    """
    detections = _try_parse_json(raw_text)
    if detections is not None:
        return detections

    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw_text)
    if code_block:
        detections = _try_parse_json(code_block.group(1))
        if detections is not None:
            return detections

    array_match = re.search(r"\[[\s\S]*\]", raw_text)
    if array_match:
        detections = _try_parse_json(array_match.group(0))
        if detections is not None:
            return detections

    return _parse_freetext(raw_text)


def _try_parse_json(text: str) -> list[Detection] | None:
    try:
        data = json.loads(text.strip())
        if not isinstance(data, list):
            return None
        results = []
        for item in data:
            if not isinstance(item, dict):
                continue
            label = item.get("label", "unknown_vessel")
            confidence = float(item.get("confidence", 0.9))
            bbox = item.get("bbox", None)
            if bbox and len(bbox) == 4:
                bbox = [float(v) for v in bbox]
                bbox = [max(0.0, min(1.0, v)) for v in bbox]
                results.append(Detection(label=label, confidence=confidence, bbox=bbox))
        return results
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


_VESSEL_KEYWORDS = [
    "ship", "vessel", "boat", "tanker", "cargo", "fishing",
    "patrol", "sailboat", "barge", "ferry", "yacht",
]

_POSITION_MAP = {
    "upper-left": [0.05, 0.05, 0.25, 0.25],
    "upper-center": [0.3, 0.05, 0.7, 0.25],
    "upper-right": [0.75, 0.05, 0.95, 0.25],
    "center-left": [0.05, 0.3, 0.25, 0.7],
    "center": [0.3, 0.3, 0.7, 0.7],
    "center-right": [0.75, 0.3, 0.95, 0.7],
    "lower-left": [0.05, 0.75, 0.25, 0.95],
    "lower-center": [0.3, 0.75, 0.7, 0.95],
    "lower-right": [0.75, 0.75, 0.95, 0.95],
    "top": [0.3, 0.05, 0.7, 0.25],
    "bottom": [0.3, 0.75, 0.7, 0.95],
    "left": [0.05, 0.3, 0.25, 0.7],
    "right": [0.75, 0.3, 0.95, 0.7],
}

_LABEL_MAP = {
    "cargo": "cargo_ship",
    "container": "cargo_ship",
    "tanker": "tanker",
    "fishing": "fishing_boat",
    "patrol": "patrol_vessel",
    "sailboat": "sailboat",
    "yacht": "sailboat",
    "ferry": "passenger_ferry",
    "cruise": "cruise_ship",
    "barge": "cargo_ship",
    "tug": "tugboat",
}


def _parse_freetext(text: str) -> list[Detection]:
    """Extract approximate detections from free-text scene descriptions."""
    text_lower = text.lower()

    if "no vessels" in text_lower and "detected" in text_lower:
        return []

    if not any(kw in text_lower for kw in _VESSEL_KEYWORDS):
        return []

    detections = []

    vessel_lines = re.findall(r"vessel:\s*(.+)", text_lower)
    if vessel_lines:
        for line in vessel_lines:
            parts = [p.strip() for p in line.split(",")]
            label = "unknown_vessel"
            bbox = [0.3, 0.3, 0.7, 0.7]

            for part in parts:
                for kw, lbl in _LABEL_MAP.items():
                    if kw in part:
                        label = lbl
                        break
                for pos_name, pos_bbox in _POSITION_MAP.items():
                    if pos_name in part:
                        bbox = pos_bbox
                        break

            detections.append(Detection(label=label, confidence=0.55, bbox=bbox))
        return detections

    sentences = re.split(r"[.;\n]", text)
    seen_positions = set()
    for sentence in sentences:
        s = sentence.lower().strip()
        if not any(kw in s for kw in _VESSEL_KEYWORDS):
            continue

        label = "unknown_vessel"
        for kw, lbl in _LABEL_MAP.items():
            if kw in s:
                label = lbl
                break

        bbox = [0.3, 0.3, 0.7, 0.7]
        for pos_name, pos_bbox in _POSITION_MAP.items():
            if pos_name in s:
                bbox = pos_bbox
                break

        pos_key = tuple(bbox)
        if pos_key in seen_positions:
            bbox = [b + 0.05 for b in bbox]
        seen_positions.add(pos_key)

        detections.append(Detection(label=label, confidence=0.50, bbox=bbox))

    return detections
