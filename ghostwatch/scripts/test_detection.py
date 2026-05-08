"""Standalone test for the GhostWatch detection pipeline.

Tests vessel detection, ghost analysis, and dispatch generation
without needing the full API server running.

Usage:
    GHOSTWATCH_MOCK_MODE=true python -m ghostwatch.scripts.test_detection
    python -m ghostwatch.scripts.test_detection
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

if "GHOSTWATCH_MOCK_MODE" not in os.environ:
    os.environ["GHOSTWATCH_MOCK_MODE"] = "true"

from ghostwatch.detector.vlm_detector import VesselDetector
from ghostwatch.detector.bbox_utils import bbox_to_latlon
from ghostwatch.ais.synthetic_ais import SyntheticAISFeed
from ghostwatch.ais.ghost_logic import GhostAnalyzer
from ghostwatch.dispatch.drone_dispatch import generate_dispatch


def main():
    print("=" * 60)
    print("GhostWatch Detection Pipeline Test")
    print("=" * 60)

    print("\n[1] Initializing detector...")
    detector = VesselDetector()
    print(f"    Model ready: {detector.is_ready}")

    print("\n[2] Running vessel detection...")
    from PIL import Image
    test_image = Image.new("RGB", (512, 512), color=(20, 40, 80))
    detections = detector.detect(test_image)
    print(f"    Detected {len(detections)} vessels:")
    for d in detections:
        print(f"      - {d.label} (conf={d.confidence:.2f}, bbox={[round(v, 3) for v in d.bbox]})")

    print("\n[3] Converting to coordinates...")
    footprint = [103.6, 1.1, 104.0, 1.4]
    coords = [bbox_to_latlon(d.bbox, footprint) for d in detections]
    for (lat, lon), d in zip(coords, detections):
        print(f"      {d.label}: ({lat:.4f}, {lon:.4f})")

    print("\n[4] Getting AIS data...")
    ais_feed = SyntheticAISFeed()
    ais_vessels = ais_feed.get_vessels_in_region(*footprint)
    print(f"    Found {len(ais_vessels)} AIS vessels:")
    for v in ais_vessels:
        print(f"      - {v.vessel_name} ({v.vessel_type}, AIS={v.ais_status})")

    print("\n[5] Running ghost analysis...")
    analyzer = GhostAnalyzer()
    ghost_results = analyzer.analyze(detections, coords, ais_vessels, "TEST")
    ghost_count = sum(1 for g in ghost_results if g.ghost_status == "ghost")
    matched_count = sum(1 for g in ghost_results if g.ghost_status == "matched")
    print(f"    Results: {len(ghost_results)} total, {ghost_count} ghost, {matched_count} matched")
    for g in ghost_results:
        marker = "[GHOST]" if g.ghost_status == "ghost" else "[OK]" if g.ghost_status == "matched" else "[?]"
        print(f"      {marker} {g.detection_id}: {g.ghost_status} (risk={g.risk_score})")
        print(f"         {g.reason}")

    print("\n[6] Generating drone dispatches...")
    for g in ghost_results:
        if g.ghost_status == "ghost":
            dispatch = generate_dispatch(g)
            print(f"      Dispatch {dispatch.dispatch_id}:")
            print(f"        Priority: {dispatch.priority}")
            print(f"        Scan radius: {dispatch.scan_radius_km} km")
            print(f"        Payload: {json.dumps(dispatch.mission_payload.model_dump(), indent=2)[:200]}...")

    print("\n" + "=" * 60)
    print("Pipeline test complete!")
    print("=" * 60)

    print("\n[SAMPLE API RESPONSE]")
    sample = {
        "scan_id": "GW-TEST01",
        "timestamp": "2026-04-13T12:00:00Z",
        "detections": [
            {
                "detection_id": g.detection_id,
                "label": g.label,
                "confidence": g.confidence,
                "bbox": g.bbox,
                "coordinates": {"lat": g.lat, "lon": g.lon},
                "estimated_type": g.estimated_type,
                "ghost_status": g.ghost_status,
                "risk_score": g.risk_score,
                "reason": g.reason,
            }
            for g in ghost_results
        ],
        "summary": {
            "total_vessels": len(ghost_results),
            "ghost_vessels": ghost_count,
            "matched_vessels": matched_count,
            "dispatches_recommended": ghost_count,
        },
    }
    print(json.dumps(sample, indent=2))


if __name__ == "__main__":
    main()
