import React, { useEffect, useRef } from "react";
import type { TelemetryPoint } from "./api";
import type { DetectionResult, Coordinates } from "./ghostwatch-api";
import * as Cesium from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";

interface GlobeViewProps {
  telemetry: TelemetryPoint[];
  detections?: DetectionResult[];
  scanCenter?: Coordinates | null;
  scanId?: string | null;
  scanSizeKm?: number | null;
  droneTarget?: Coordinates | null;
  onMapClick?: (lat: number, lon: number) => void;
}

const statusColors: Record<string, Cesium.Color> = {
  ghost: Cesium.Color.RED,
  anomalous: Cesium.Color.YELLOW,
  matched: Cesium.Color.LIME,
};

export const GlobeView: React.FC<GlobeViewProps> = ({
  telemetry,
  detections = [],
  scanCenter = null,
  scanId = null,
  scanSizeKm = null,
  droneTarget = null,
  onMapClick,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const viewerRef = useRef<any>(null);
  const onMapClickRef = useRef(onMapClick);
  useEffect(() => { onMapClickRef.current = onMapClick; }, [onMapClick]);

  // Init Cesium viewer once
  useEffect(() => {
    if (!containerRef.current) return;

    if (!(window as any).CESIUM_BASE_URL) {
      (window as any).CESIUM_BASE_URL = "/static/cesium/";
    }

    const viewer = new Cesium.Viewer(containerRef.current, {
      animation: false,
      timeline: false,
      baseLayerPicker: false,
      geocoder: false,
      homeButton: false,
      sceneModePicker: false,
      navigationHelpButton: false,
      fullscreenButton: false,
      terrainProvider: new Cesium.EllipsoidTerrainProvider(),
    });

    // @ts-ignore — pre-existing from SimSat
    viewer.scene.skyBox.show = false;
    // @ts-ignore
    viewer.scene.skyAtmosphere.show = false;

    viewer.imageryLayers.removeAll();
    viewer.imageryLayers.addImageryProvider(
      new Cesium.UrlTemplateImageryProvider({
        url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        credit: "© Esri",
        maximumLevel: 19,
      })
    );

    viewer.camera.setView({
      destination: Cesium.Cartesian3.fromDegrees(0, 20, 15000000),
    });

    const clickHandler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    clickHandler.setInputAction((evt: any) => {
      const cb = onMapClickRef.current;
      if (!cb) return;
      const cartesian = viewer.scene.pickPosition(evt.position) ||
        viewer.camera.pickEllipsoid(evt.position, viewer.scene.globe.ellipsoid);
      if (!cartesian) return;
      const carto = Cesium.Cartographic.fromCartesian(cartesian);
      const lat = Cesium.Math.toDegrees(carto.latitude);
      const lon = Cesium.Math.toDegrees(carto.longitude);
      cb(lat, lon);
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

    viewerRef.current = viewer;

    return () => {
      if (viewerRef.current && !viewerRef.current.isDestroyed?.()) {
        viewerRef.current.destroy();
      }
    };
  }, []);

  // Update satellite position
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || !telemetry.length) return;

    telemetry.forEach((point) => {
      let entity = viewer.entities.getById(point.satellite);
      const position = Cesium.Cartesian3.fromDegrees(
        point.longitude,
        point.latitude,
        (point.altitude ?? 0) * 1000,
      );

      if (!entity) {
        entity = viewer.entities.add({
          id: point.satellite,
          position,
          point: { pixelSize: 12, color: Cesium.Color.CYAN },
          label: {
            text: "SAT",
            font: "bold 10px system-ui",
            fillColor: Cesium.Color.CYAN,
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            outlineWidth: 2,
            outlineColor: Cesium.Color.BLACK,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            pixelOffset: new Cesium.Cartesian2(0, -14),
            showBackground: true,
            backgroundColor: new Cesium.Color(0, 0, 0, 0.5),
            backgroundPadding: new Cesium.Cartesian2(4, 3),
          },
        });
      } else {
        entity.position = position as any;
      }
    });
  }, [telemetry]);

  // Fly to scan area when scanId changes (new scan completed)
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || !scanCenter || !scanId) return;

    // Remove old scan markers
    viewer.entities.removeById("scan-center");
    viewer.entities.removeById("scan-area");

    // Scan center crosshair
    viewer.entities.add({
      id: "scan-center",
      position: Cesium.Cartesian3.fromDegrees(scanCenter.lon, scanCenter.lat, 0),
      point: {
        pixelSize: 8,
        color: Cesium.Color.fromAlpha(Cesium.Color.CYAN, 0.8),
        outlineColor: Cesium.Color.WHITE,
        outlineWidth: 2,
      },
      label: {
        text: "SCAN AREA",
        font: "bold 11px system-ui",
        fillColor: Cesium.Color.CYAN,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        outlineWidth: 2,
        outlineColor: Cesium.Color.BLACK,
        verticalOrigin: Cesium.VerticalOrigin.TOP,
        pixelOffset: new Cesium.Cartesian2(0, 12),
        showBackground: true,
        backgroundColor: new Cesium.Color(0, 0, 0, 0.6),
        backgroundPadding: new Cesium.Cartesian2(6, 4),
      },
    });

    // Scan footprint rectangle — sized from explicit prop (km → degrees, lat-corrected)
    const sizeKm = scanSizeKm ?? 1.5;
    const dLat = (sizeKm / 111.0) / 2;
    const dLon = dLat / Math.max(0.05, Math.cos(scanCenter.lat * Math.PI / 180));
    viewer.entities.add({
      id: "scan-area",
      rectangle: {
        coordinates: Cesium.Rectangle.fromDegrees(
          scanCenter.lon - dLon, scanCenter.lat - dLat,
          scanCenter.lon + dLon, scanCenter.lat + dLat,
        ),
        material: Cesium.Color.CYAN.withAlpha(0.12),
        outline: true,
        outlineColor: Cesium.Color.CYAN.withAlpha(0.5),
      },
    });

    // Fly camera up to ~250 km altitude — gives nice regional context
    // (coastline visible) without zooming to street level.
    viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(scanCenter.lon, scanCenter.lat, 250000),
      orientation: {
        heading: 0,
        pitch: Cesium.Math.toRadians(-90),
        roll: 0,
      },
      duration: 1.2,
    });
  }, [scanId]); // scanId changes on every new scan

  // Drone entity — appears when dispatch confirmed
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    // Remove old drone entities
    viewer.entities.removeById("drone");
    viewer.entities.removeById("drone-radius");

    if (!droneTarget) return;

    // Drone marker
    viewer.entities.add({
      id: "drone",
      position: Cesium.Cartesian3.fromDegrees(droneTarget.lon, droneTarget.lat, 500),
      point: {
        pixelSize: 10,
        color: Cesium.Color.fromCssColorString("#3b82f6"),
        outlineColor: Cesium.Color.WHITE,
        outlineWidth: 2,
      },
      label: {
        text: "DRONE ACTIVE",
        font: "bold 11px system-ui",
        fillColor: Cesium.Color.fromCssColorString("#3b82f6"),
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        outlineWidth: 2,
        outlineColor: Cesium.Color.BLACK,
        verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
        pixelOffset: new Cesium.Cartesian2(0, -16),
        showBackground: true,
        backgroundColor: new Cesium.Color(0, 0, 0, 0.7),
        backgroundPadding: new Cesium.Cartesian2(6, 4),
      },
    });

    // Investigation radius circle
    viewer.entities.add({
      id: "drone-radius",
      position: Cesium.Cartesian3.fromDegrees(droneTarget.lon, droneTarget.lat, 0),
      ellipse: {
        semiMajorAxis: 2000,
        semiMinorAxis: 2000,
        material: Cesium.Color.fromCssColorString("#3b82f6").withAlpha(0.08),
        outline: true,
        outlineColor: Cesium.Color.fromCssColorString("#3b82f6").withAlpha(0.5),
        outlineWidth: 2,
      },
    });

    // Fly camera to drone
    viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(droneTarget.lon, droneTarget.lat, 15000),
      orientation: {
        heading: 0,
        pitch: Cesium.Math.toRadians(-90),
        roll: 0,
      },
      duration: 1.5,
    });
  }, [droneTarget]);

  // Update detection entities
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    // Remove old detection entities
    const toRemove: string[] = [];
    viewer.entities.values.forEach((e: any) => {
      if (e.id && typeof e.id === "string" && e.id.startsWith("det-")) {
        toRemove.push(e.id);
      }
    });
    toRemove.forEach((id: string) => viewer.entities.removeById(id));

    // Add new
    detections.forEach((det) => {
      const color = statusColors[det.ghost_status] || Cesium.Color.WHITE;

      viewer.entities.add({
        id: `det-${det.detection_id}`,
        position: Cesium.Cartesian3.fromDegrees(det.coordinates.lon, det.coordinates.lat, 0),
        point: {
          pixelSize: det.ghost_status === "ghost" ? 7 : 5,
          color: color,
          outlineColor: Cesium.Color.WHITE,
          outlineWidth: 1,
        },
        label: {
          text: det.ghost_status === "ghost"
            ? `Risk ${det.risk_score}`
            : det.estimated_type.replace(/_/g, " "),
          font: "9px system-ui",
          fillColor: color,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          outlineWidth: 1,
          outlineColor: Cesium.Color.BLACK,
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          pixelOffset: new Cesium.Cartesian2(0, -10),
          showBackground: true,
          backgroundColor: new Cesium.Color(0, 0, 0, 0.5),
          backgroundPadding: new Cesium.Cartesian2(4, 2),
        },
      });
    });
  }, [detections]);

  return <div ref={containerRef} className="globe-view" />;
};
