"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useThesis } from "@/lib/thesis/context";
import type { RankedPick } from "@/lib/thesis";
import { InfoTip } from "./InfoTip";
import {
  Avatar,
  EpistemeBar,
  fmtMoney,
  fmtScore,
  OutcomeChip,
  ScoreSpark,
  ViewIntro,
} from "./primitives";

interface FounderRowProps {
  row: RankedPick & { _t: number };
  rank: number;
  alloc: number;
  focused: boolean;
  prevRank?: number;
  onClick: () => void;
}

function FounderRow({ row, rank, alloc, focused, prevRank, onClick }: FounderRowProps) {
  const delta = prevRank == null ? 0 : prevRank - rank;
  return (
    <div
      className={"founder-row " + (focused ? "focused" : "")}
      onClick={onClick}
    >
      <div className="col-rank">
        <span className="rank-num">{String(rank + 1).padStart(2, "0")}</span>
        {delta !== 0 && (
          <span className={"rank-delta " + (delta > 0 ? "up" : "down")}>
            {delta > 0 ? "▲" : "▼"}
            {Math.abs(delta)}
          </span>
        )}
      </div>
      <div className="col-id">
        <Avatar id={row.id} name={row.name} />
        <div className="id-block">
          <span className="handle">@{row.id}</span>
          <span className="name">
            {row.name} · <span className="muted">{row.niche}</span>
          </span>
        </div>
      </div>
      <div className="col-scores">
        <div className="score-pair">
          <span className="score-label">T1</span>
          <span className="score-val">{fmtScore(row.t1)}</span>
        </div>
        <div className="score-pair">
          <span className="score-label">T2</span>
          <span className="score-val">{fmtScore(row.t2)}</span>
        </div>
        <div className="score-pair primary">
          <span className="score-label">Σ</span>
          <span className="score-val">{fmtScore(row.combined)}</span>
        </div>
        <span className="spark-wrap">
          <ScoreSpark founderId={row.id} tNow={row._t} />
        </span>
      </div>
      <div className="col-alloc mono">{fmtMoney(alloc)}</div>
      <div className="col-outcome">
        <OutcomeChip outcome={row.outcome} />
      </div>
    </div>
  );
}

interface AuditEntry {
  kind: "enter" | "exit" | "shift";
  id: string;
  rank?: number;
  prev?: number;
  dRank?: number;
}

function AuditLog({ entries }: { entries: AuditEntry[] }) {
  return (
    <div className="audit">
      <div className="audit-list">
        {entries.length === 0 && (
          <div className="audit-empty muted">— slider steady. no membership changes.</div>
        )}
        {entries.slice(0, 8).map((e, i) => (
          <div key={i} className={"audit-row " + e.kind}>
            <span className={"audit-glyph " + e.kind}>
              {e.kind === "enter" ? "→" : e.kind === "exit" ? "←" : "•"}
            </span>
            <span className="audit-name">@{e.id}</span>
            <span className="audit-meta mono muted">
              {e.kind === "enter"
                ? `entered #${(e.rank ?? 0) + 1}`
                : e.kind === "exit"
                ? `exited (was #${(e.prev ?? 0) + 1})`
                : `Δ ${(e.dRank ?? 0) > 0 ? "+" : ""}${e.dRank} → #${(e.rank ?? 0) + 1}`}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function KGMini({
  rows,
  focusedId,
  onFocus,
}: {
  rows: RankedPick[];
  focusedId: string;
  onFocus: (id: string) => void;
}) {
  const size = 200;
  const cx = size / 2;
  const cy = size / 2;
  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="kg-mini">
      <defs>
        <radialGradient id="kgglow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.14" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle cx={cx} cy={cy} r={cx - 4} fill="url(#kgglow)" />
      {[0.4, 0.65, 0.9].map((r, i) => (
        <circle
          key={i}
          cx={cx}
          cy={cy}
          r={r * (cx - 6)}
          fill="none"
          stroke="var(--hairline-2)"
          strokeDasharray="2 3"
        />
      ))}
      {rows.slice(0, 10).map((_row, i) => {
        const a = (i / rows.length) * Math.PI * 2;
        const r = 0.45 + (1 - i / rows.length) * 0.45;
        const x1 = cx + Math.cos(a) * (cx - 8) * r;
        const y1 = cy + Math.sin(a) * (cx - 8) * r;
        const j = (i + 3) % rows.length;
        const aj = (j / rows.length) * Math.PI * 2;
        const rj = 0.45 + (1 - j / rows.length) * 0.45;
        const x2 = cx + Math.cos(aj) * (cx - 8) * rj;
        const y2 = cy + Math.sin(aj) * (cx - 8) * rj;
        return (
          <line
            key={"e" + i}
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y2}
            stroke="var(--accent)"
            strokeOpacity="0.16"
            strokeWidth="0.6"
          />
        );
      })}
      {rows.map((row, i) => {
        const a = (i / rows.length) * Math.PI * 2 - Math.PI / 2;
        const r = 0.5 + (1 - i / rows.length) * 0.42;
        const x = cx + Math.cos(a) * (cx - 8) * r;
        const y = cy + Math.sin(a) * (cx - 8) * r;
        const ptSize = 2.4 + row.combined * 5;
        const focused = focusedId === row.id;
        return (
          <g
            key={row.id}
            onClick={() => onFocus(row.id)}
            style={{ cursor: "pointer" }}
          >
            <circle cx={x} cy={y} r={ptSize + 2} fill="var(--accent)" opacity={focused ? 0.32 : 0.10} />
            <circle
              cx={x}
              cy={y}
              r={ptSize}
              fill={focused ? "var(--accent)" : "var(--ink-1)"}
              opacity={0.4 + row.combined * 0.6}
            />
            {focused && (
              <circle cx={x} cy={y} r={ptSize + 5} fill="none" stroke="var(--accent)" strokeWidth="1.2" />
            )}
          </g>
        );
      })}
      <text
        x={cx}
        y={cy + 3}
        textAnchor="middle"
        fontFamily="var(--mono)"
        fontSize="10"
        fill="var(--ink-3)"
        fontWeight="500"
      >
        N={rows.length}
      </text>
    </svg>
  );
}

interface PortfolioProps {
  rows: RankedPick[];
  capital: number;
  focusedId: string;
  onFocus: (id: string) => void;
  t: number;
  prevRanks: Record<string, number>;
}

function Portfolio({ rows, capital, focusedId, onFocus, t, prevRanks }: PortfolioProps) {
  const allocs = useMemo(() => {
    const total = capital * 1_000_000;
    return rows.map(() => total / rows.length);
  }, [rows, capital]);
  return (
    <div className="portfolio">
      <div className="portfolio-head">
        <div className="col-rank">#</div>
        <div className="col-id">Founder</div>
        <div className="col-scores">
          <span style={{ marginRight: 8 }}>Scores</span>
          <InfoTip width={320}>
            <strong>T1 · Tier-1 score.</strong> Raw social-signal model (gradient-boosted classifier on dimensions <span className="mono">S1–S6</span> from the taxonomy). Range <span className="mono">[0,1]</span>.
            <br /><br />
            <strong>T2 · Tier-2 score.</strong> KG-augmented re-ranker. Takes T1 + features extracted from the founder&apos;s ego-network (mentors, peers, distribution loops).
            <br /><br />
            <strong>Σ · Combined.</strong> The ranking score. <span className="mono">Σ = 0.4·T1 + 0.6·T2</span>. Founders sorted by Σ descending.
          </InfoTip>
        </div>
        <div className="col-alloc">
          Allocation
          <InfoTip width={260}>
            Per-founder dollars under the current allocation rule (default: equal-weight across K). Change in Settings.
          </InfoTip>
        </div>
        <div className="col-outcome">
          Outcome @ T+24mo
          <InfoTip width={300}>
            Did this founder launch a fundable venture within 24 months of date T? <span className="mono">●</span> emerged, <span className="mono">○</span> not yet, <span className="mono">?</span> horizon still in the future (hidden by the lookahead-bias guard).
          </InfoTip>
        </div>
      </div>
      <div className="portfolio-body">
        {rows.map((r, i) => (
          <FounderRow
            key={r.id}
            row={{ ...r, _t: t }}
            rank={i}
            alloc={allocs[i]}
            focused={focusedId === r.id}
            prevRank={prevRanks[r.id]}
            onClick={() => onFocus(r.id)}
          />
        ))}
      </div>
    </div>
  );
}

interface Props {
  t: number;
  K: number;
  capital: number;
  focusedId: string;
  setFocused: (id: string) => void;
  gotoView: (v: 1 | 2 | 3) => void;
  setRevealed: (b: boolean) => void;
}

export function View1Replay({
  t,
  K,
  capital,
  focusedId,
  setFocused,
  gotoView,
  setRevealed,
}: Props) {
  const thesis = useThesis();
  const rows = useMemo(() => thesis.rankAt(t, K), [t, K, thesis]);
  const prevRows = useRef(rows);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  // prevRanks is the previous frame's rank map. Lives in state so the
  // renderer (FounderRow) can read it without touching a ref during
  // render — the ref is only mutated in the post-render effect below.
  const [prevRanks, setPrevRanks] = useState<Record<string, number>>(() => {
    const m: Record<string, number> = {};
    rows.forEach((r, i) => (m[r.id] = i));
    return m;
  });

  useEffect(() => {
    const prev = prevRows.current;
    const prevSet = new Set(prev.map(r => r.id));
    const nowSet = new Set(rows.map(r => r.id));
    const entries: AuditEntry[] = [];
    rows.forEach((r, i) => {
      if (!prevSet.has(r.id)) entries.push({ kind: "enter", id: r.id, rank: i });
    });
    prev.forEach((r, i) => {
      if (!nowSet.has(r.id)) entries.push({ kind: "exit", id: r.id, prev: i });
    });
    rows.forEach((r, i) => {
      const pi = prev.findIndex(x => x.id === r.id);
      if (pi >= 0 && Math.abs(pi - i) >= 3) {
        entries.push({ kind: "shift", id: r.id, rank: i, dRank: pi - i });
      }
    });
    if (entries.length > 0) {
      setAudit(prevA => [...entries.slice(0, 6), ...prevA].slice(0, 12));
    }
    const nextRanks: Record<string, number> = {};
    prev.forEach((r, i) => (nextRanks[r.id] = i));
    setPrevRanks(nextRanks);
    prevRows.current = rows;
  }, [t, rows]);

  const t24 = t + 24;
  const canReveal = t24 <= thesis.today;

  return (
    <section className="view view-1">
      <ViewIntro kicker="STEP 01 · PICK" title="Who would the framework have backed?">
        These are the top <span className="mono">{K}</span> founders ranked by combined score at <strong>{thesis.fmtMonth(t)}</strong>.<strong> Drag the slider</strong> to replay the past — picks reshuffle in real time, with no information from after that date.<strong> Click any row</strong> to focus a founder; come back here later to drill in.
      </ViewIntro>

      <div className="grid-2">
        <div className="center">
          <Portfolio
            rows={rows}
            capital={capital}
            focusedId={focusedId}
            onFocus={setFocused}
            t={t}
            prevRanks={prevRanks}
          />
          <div className="portfolio-foot">
            <span className="muted">
              {rows.length} picks · cohort pool N=
              {
                thesis.founders().filter(f => {
                  const m = thesis.months(f.first);
                  return m != null && m <= t;
                }).length
              }
            </span>
            <button
              className={"reveal-btn " + (canReveal ? "" : "disabled")}
              disabled={!canReveal}
              onClick={() => {
                setRevealed(true);
                gotoView(2);
              }}
              title={canReveal ? "See how the picks performed" : "T+24mo is still in the future"}
            >
              {canReveal ? "Score these picks" : "Outcomes locked"}
              {canReveal && <span className="reveal-arrow"> →</span>}
            </button>
          </div>
        </div>

        <aside className="side-rail">
          <div className="rail-card">
            <div className="rail-head">
              <span className="kicker">Knowledge graph</span>
              <InfoTip width={300}>
                Each dot is one founder in the top-K. Position is decorative; <strong>size = Σ score</strong>. Faint edges hint at shared topics / mentors. Click a dot to focus.
              </InfoTip>
            </div>
            <KGMini rows={rows} focusedId={focusedId} onFocus={setFocused} />
          </div>
          <div className="rail-card">
            <div className="rail-head">
              <span className="kicker">What just changed</span>
              <InfoTip width={280}>
                Live diff of the top-K membership. Green = entered, red = exited, grey = moved by ≥ 3 places. Useful for showing the slider&apos;s effect.
              </InfoTip>
            </div>
            <AuditLog entries={audit} />
          </div>
        </aside>
      </div>

      <EpistemeBar>
        Picks based on signals observable <strong>at date T only</strong>. The bias guard (top-right) is active: future information is hidden. Outcomes are shown only when T+24mo has elapsed.
      </EpistemeBar>
    </section>
  );
}
