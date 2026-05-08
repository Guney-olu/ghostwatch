import React, { useEffect, useRef, useState } from "react";
import {
  REGIONS,
  MonitorRegion,
  RegionCategory,
  CATEGORY_LABELS,
  CATEGORY_COLORS,
} from "./regions";

interface Props {
  active: MonitorRegion;
  onSelect: (region: MonitorRegion) => void;
}

const CATEGORY_ORDER: RegionCategory[] = ["CHOKEPOINT", "IUU", "STRATEGIC", "PORT"];

export const RegionSelector: React.FC<Props> = ({ active, onSelect }) => {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState<RegionCategory | "ALL">("ALL");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const visible = filter === "ALL" ? REGIONS : REGIONS.filter((r) => r.category === filter);

  const grouped: Record<string, MonitorRegion[]> = {};
  for (const r of visible) {
    if (!grouped[r.category]) grouped[r.category] = [];
    grouped[r.category].push(r);
  }

  return (
    <div className="region-selector" ref={ref}>
      <button
        className={`region-trigger ${open ? "open" : ""}`}
        onClick={() => setOpen((v) => !v)}
        title="Select monitoring region"
      >
        <span className="region-trigger-prefix">TARGET</span>
        <span className="region-trigger-divider" />
        <span className="region-trigger-flag">{active.flag}</span>
        <span className="region-trigger-text">
          <span className="region-trigger-name">{active.name}</span>
          <span
            className="region-trigger-cat"
            style={{ color: CATEGORY_COLORS[active.category] }}
          >
            {CATEGORY_LABELS[active.category]}
          </span>
        </span>
        <span className="region-trigger-coords">
          {active.lat.toFixed(2)}°{active.lat >= 0 ? "N" : "S"}
          {"  "}
          {active.lon.toFixed(2)}°{active.lon >= 0 ? "E" : "W"}
        </span>
        <span className={`region-trigger-chevron ${open ? "open" : ""}`}>▾</span>
      </button>

      {open && (
        <div className="region-dropdown">
          <div className="region-dropdown-header">
            <div className="region-dropdown-title">SELECT MONITORING TARGET</div>
            <div className="region-dropdown-filters">
              <button
                className={`region-filter ${filter === "ALL" ? "active" : ""}`}
                onClick={() => setFilter("ALL")}
              >
                All
              </button>
              {CATEGORY_ORDER.map((cat) => (
                <button
                  key={cat}
                  className={`region-filter ${filter === cat ? "active" : ""}`}
                  style={
                    filter === cat
                      ? {
                          color: CATEGORY_COLORS[cat],
                          borderColor: CATEGORY_COLORS[cat] + "55",
                          background: CATEGORY_COLORS[cat] + "1a",
                        }
                      : undefined
                  }
                  onClick={() => setFilter(cat)}
                >
                  {CATEGORY_LABELS[cat]}
                </button>
              ))}
            </div>
          </div>

          <div className="region-dropdown-list">
            {CATEGORY_ORDER.flatMap((cat) => {
              const items = grouped[cat];
              if (!items || items.length === 0) return [];
              return [
                <div key={`${cat}-h`} className="region-group-header">
                  <span
                    className="region-group-dot"
                    style={{ background: CATEGORY_COLORS[cat] }}
                  />
                  {CATEGORY_LABELS[cat]}
                  <span className="region-group-count">{items.length}</span>
                </div>,
                ...items.map((r) => (
                  <button
                    key={r.id}
                    className={`region-option ${active.id === r.id ? "active" : ""}`}
                    onClick={() => {
                      onSelect(r);
                      setOpen(false);
                    }}
                  >
                    <span className="region-option-flag">{r.flag}</span>
                    <span className="region-option-body">
                      <span className="region-option-name">{r.name}</span>
                      <span className="region-option-sub">{r.subtitle}</span>
                    </span>
                    <span className="region-option-coords">
                      {r.lat.toFixed(2)}°{r.lat >= 0 ? "N" : "S"} ·{" "}
                      {r.lon.toFixed(2)}°{r.lon >= 0 ? "E" : "W"}
                    </span>
                  </button>
                )),
              ];
            })}
          </div>
        </div>
      )}
    </div>
  );
};
