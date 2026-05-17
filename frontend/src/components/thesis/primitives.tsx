"use client";

import { useMemo } from "react";
import { thesis } from "@/lib/thesis";
import type { Outcome } from "@/lib/thesis";

export function fmtPct(x: number, digits = 1): string {
  return (x * 100).toFixed(digits) + "%";
}
export function fmtScore(x: number | null | undefined): string {
  return x == null ? "—" : x.toFixed(2);
}
export function fmtMoney(x: number): string {
  return "$" + x.toLocaleString("en-US");
}

export function OutcomeChip({ outcome }: { outcome: Outcome }) {
  const map: Record<Outcome, { c: string; bg: string; label: string; glyph: string }> = {
    emerged: { c: "var(--ok)", bg: "rgba(46,164,79,0.10)", label: "emerged", glyph: "●" },
    not_yet: { c: "var(--no)", bg: "rgba(203,36,49,0.08)", label: "not yet", glyph: "○" },
    unknown: { c: "var(--mu)", bg: "rgba(149,157,165,0.10)", label: "unknown", glyph: "?" },
  };
  const s = map[outcome];
  return (
    <span
      className="chip"
      style={{ color: s.c, background: s.bg, borderColor: s.c }}
    >
      <span style={{ fontFamily: "var(--mono)", marginRight: 4 }}>{s.glyph}</span>
      {s.label}
    </span>
  );
}

export function Avatar({ id, name, size = 28 }: { id: string; name: string; size?: number }) {
  const p = thesis.paletteFor(id);
  const initials = name.split(/\s+/).map(x => x[0]).slice(0, 2).join("");
  return (
    <span
      className="avatar"
      style={{
        width: size,
        height: size,
        background: `linear-gradient(135deg, ${p.c1}, ${p.c2})`,
        fontSize: size * 0.42,
      }}
    >
      {initials}
    </span>
  );
}

export function ScoreSpark({
  founderId,
  tNow,
  width = 60,
  height = 18,
}: {
  founderId: string;
  tNow: number;
  width?: number;
  height?: number;
}) {
  const points = useMemo(() => {
    const f = thesis.founders().find(x => x.id === founderId);
    if (!f) return [] as Array<[number, number]>;
    const fm = thesis.months(f.first);
    if (fm == null) return [];
    const pts: Array<[number, number]> = [];
    for (let i = 0; i <= 24; i++) {
      const t = fm + i * 2;
      if (t > tNow) break;
      const c = thesis.curve(f, t);
      if (c == null) continue;
      pts.push([t, c]);
    }
    return pts;
  }, [founderId, tNow]);
  if (points.length < 2) return <svg width={width} height={height} />;
  const xs = points.map(p => p[0]);
  const xmin = Math.min(...xs);
  const xmax = Math.max(...xs);
  const path = points
    .map(([t, c], i) => {
      const x = ((t - xmin) / Math.max(xmax - xmin, 1)) * (width - 2) + 1;
      const y = height - c * (height - 2) - 1;
      return (i ? "L" : "M") + x.toFixed(1) + "," + y.toFixed(1);
    })
    .join(" ");
  return (
    <svg width={width} height={height} className="spark">
      <path d={path} fill="none" stroke="currentColor" strokeWidth="1" />
    </svg>
  );
}

export function CIBar({
  value,
  lo,
  hi,
  width = 240,
  primary = false,
}: {
  value: number;
  lo: number;
  hi: number;
  width?: number;
  primary?: boolean;
}) {
  const px = (v: number) => v * width;
  return (
    <div className="ci-bar" style={{ width }}>
      <div className="ci-axis" />
      <div
        className="ci-range"
        style={{
          left: px(lo),
          width: px(hi - lo),
          background: primary ? "var(--accent)" : "var(--ink-3)",
        }}
      />
      <div
        className="ci-mean"
        style={{ left: px(value), background: primary ? "var(--accent-deep)" : "var(--ink-1)" }}
      />
      <div className="ci-tick" style={{ left: px(lo) }} />
      <div className="ci-tick" style={{ left: px(hi) }} />
    </div>
  );
}

export function EpistemeBar({ children }: { children: React.ReactNode }) {
  return (
    <div className="episteme">
      <span className="ep-mark">ⓘ</span>
      <span>{children}</span>
    </div>
  );
}

export function ViewIntro({
  kicker,
  title,
  children,
}: {
  kicker: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="view-intro">
      <div className="view-intro-left">
        <span className="kicker">{kicker}</span>
        <span className="view-intro-title">{title}</span>
      </div>
      <div className="view-intro-body">{children}</div>
    </div>
  );
}

export function Footer() {
  return (
    <footer className="footer">
      <div>
        Working artefact for thesis defence ·{" "}
        <span className="mono">2026-07-18</span>
      </div>
      <div className="muted">
        Code: <span className="mono">github.com/KR2809/the-social-media-vc-thesis</span>
      </div>
      <div className="muted">
        Frozen <span className="mono">2026-05-31</span> · build <span className="mono">scaffold</span>
      </div>
    </footer>
  );
}
