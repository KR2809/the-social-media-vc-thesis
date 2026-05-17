"use client";

import { useCallback, useEffect, useRef } from "react";
import { thesis } from "@/lib/thesis";

interface Props {
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
}

export function DateSlider({ value, onChange, min, max }: Props) {
  const ticks: number[] = [];
  for (let y = 2014; y <= 2026; y++) ticks.push((y - 2014) * 12);

  const pct = ((value - min) / (max - min)) * 100;
  const ref = useRef<HTMLDivElement | null>(null);
  const dragging = useRef(false);

  const handle = useCallback(
    (e: MouseEvent | TouchEvent | React.MouseEvent | React.TouchEvent) => {
      const node = ref.current;
      if (!node) return;
      const r = node.getBoundingClientRect();
      const clientX =
        "touches" in e
          ? (e as TouchEvent).touches[0]?.clientX ?? 0
          : (e as MouseEvent).clientX;
      const x = clientX - r.left;
      const f = Math.max(0, Math.min(1, x / r.width));
      onChange(Math.round(min + f * (max - min)));
    },
    [min, max, onChange],
  );

  useEffect(() => {
    function up() {
      dragging.current = false;
    }
    function mv(e: MouseEvent | TouchEvent) {
      if (dragging.current) handle(e);
    }
    window.addEventListener("mouseup", up);
    window.addEventListener("touchend", up);
    window.addEventListener("mousemove", mv);
    window.addEventListener("touchmove", mv);
    return () => {
      window.removeEventListener("mouseup", up);
      window.removeEventListener("touchend", up);
      window.removeEventListener("mousemove", mv);
      window.removeEventListener("touchmove", mv);
    };
  }, [handle]);

  return (
    <div className="slider-wrap">
      <div className="slider-label">
        <span className="kicker">COHORT DATE T</span>
        <span className="slider-value">
          {thesis.fmtMonth(value)}{" "}
          <span className="muted">· t+24mo {thesis.fmtMonth(value + 24)}</span>
        </span>
      </div>
      <div
        className="slider-track"
        ref={ref}
        onMouseDown={e => {
          dragging.current = true;
          handle(e);
        }}
        onTouchStart={e => {
          dragging.current = true;
          handle(e);
        }}
      >
        <div className="slider-fill" style={{ width: pct + "%" }} />
        {ticks.map((t, i) => {
          const left = ((t - min) / (max - min)) * 100;
          const y = 2014 + Math.round(t / 12);
          return (
            <div
              key={i}
              className="slider-tick"
              style={{ left: left + "%" }}
            >
              <div className="tick-mark" />
              <div className="tick-label">{y}</div>
            </div>
          );
        })}
        <div className="slider-thumb" style={{ left: pct + "%" }}>
          <div className="thumb-inner" />
          <div className="thumb-line" />
        </div>
        <div
          className="slider-today"
          style={{ left: ((thesis.today - min) / (max - min)) * 100 + "%" }}
        >
          <div className="today-line" />
          <div className="today-label">TODAY</div>
        </div>
      </div>
    </div>
  );
}
