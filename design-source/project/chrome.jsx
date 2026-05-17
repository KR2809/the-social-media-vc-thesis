/* Shared chrome + small primitives for the thesis demo. */

const { useState, useEffect, useMemo, useRef, useCallback } = React;

// ---------- formatting ----------
function fmtPct(x, digits = 1) { return (x * 100).toFixed(digits) + "%"; }
function fmtScore(x) { return x == null ? "—" : x.toFixed(2); }
function fmtMoney(x) { return "$" + x.toLocaleString("en-US"); }

// ---------- outcome chip ----------
function OutcomeChip({ outcome }) {
  const map = {
    emerged: { c: "var(--ok)", bg: "rgba(46,164,79,0.10)", label: "emerged", glyph: "●" },
    not_yet: { c: "var(--no)", bg: "rgba(203,36,49,0.08)", label: "not yet",  glyph: "○" },
    unknown: { c: "var(--mu)", bg: "rgba(149,157,165,0.10)", label: "unknown", glyph: "?" }
  };
  const s = map[outcome] || map.unknown;
  return (
    <span className="chip" style={{ color: s.c, background: s.bg, borderColor: s.c }}>
      <span style={{ fontFamily: "var(--mono)", marginRight: 4 }}>{s.glyph}</span>{s.label}
    </span>
  );
}

// ---------- avatar (deterministic gradient + monogram) ----------
function Avatar({ id, name, size = 28 }) {
  const p = THESIS.paletteFor(id);
  const initials = name.split(/\s+/).map(x => x[0]).slice(0, 2).join("");
  return (
    <span className="avatar" style={{
      width: size, height: size,
      background: `linear-gradient(135deg, ${p.c1}, ${p.c2})`,
      fontSize: size * 0.42
    }}>{initials}</span>
  );
}

// ---------- sparkline of combined score ----------
function ScoreSpark({ founderId, tNow, width = 60, height = 18 }) {
  const points = useMemo(() => {
    const f = THESIS.FOUNDERS_RAW.find(x => x.id === founderId); if (!f) return [];
    const fm = THESIS.months(f.first);
    const pts = [];
    for (let i = 0; i <= 24; i++) {
      const t = fm + i * 2;
      if (t > tNow) break;
      const c = THESIS.curve(f, t); if (c == null) continue;
      pts.push([t, c]);
    }
    return pts;
  }, [founderId, tNow]);
  if (points.length < 2) return <svg width={width} height={height}></svg>;
  const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
  const xmin = Math.min(...xs), xmax = Math.max(...xs);
  const path = points.map(([t, c], i) => {
    const x = ((t - xmin) / Math.max(xmax - xmin, 1)) * (width - 2) + 1;
    const y = height - (c * (height - 2)) - 1;
    return (i ? "L" : "M") + x.toFixed(1) + "," + y.toFixed(1);
  }).join(" ");
  return (
    <svg width={width} height={height} className="spark">
      <path d={path} fill="none" stroke="currentColor" strokeWidth="1" />
    </svg>
  );
}

// ---------- CI bar ----------
function CIBar({ value, lo, hi, width = 240, primary = false }) {
  const px = v => v * width;
  return (
    <div className="ci-bar" style={{ width }}>
      <div className="ci-axis" />
      <div className="ci-range" style={{ left: px(lo), width: px(hi - lo), background: primary ? "var(--accent)" : "var(--ink-3)" }} />
      <div className="ci-mean" style={{ left: px(value), background: primary ? "var(--accent-deep)" : "var(--ink-1)" }} />
      <div className="ci-tick" style={{ left: px(lo) }} />
      <div className="ci-tick" style={{ left: px(hi) }} />
    </div>
  );
}

// ---------- date slider ----------
function DateSlider({ value, onChange, min, max }) {
  // Year ticks
  const ticks = [];
  for (let y = 2014; y <= 2026; y++) ticks.push((y - 2014) * 12);
  const pct = ((value - min) / (max - min)) * 100;
  const ref = useRef(null);
  const dragging = useRef(false);
  const handle = useCallback((e) => {
    const r = ref.current.getBoundingClientRect();
    const x = (e.touches ? e.touches[0].clientX : e.clientX) - r.left;
    const f = Math.max(0, Math.min(1, x / r.width));
    onChange(Math.round(min + f * (max - min)));
  }, [min, max, onChange]);
  useEffect(() => {
    function up() { dragging.current = false; }
    function mv(e) { if (dragging.current) handle(e); }
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
        <span className="slider-value">{THESIS.fmtMonth(value)} <span className="muted">· t+24mo {THESIS.fmtMonth(value + 24)}</span></span>
      </div>
      <div
        className="slider-track"
        ref={ref}
        onMouseDown={(e) => { dragging.current = true; handle(e); }}
        onTouchStart={(e) => { dragging.current = true; handle(e); }}
      >
        <div className="slider-fill" style={{ width: pct + "%" }} />
        {ticks.map((t, i) => {
          const left = ((t - min) / (max - min)) * 100;
          const y = 2014 + Math.round(t / 12);
          return (
            <div key={i} className="slider-tick" style={{ left: left + "%" }}>
              <div className="tick-mark" />
              <div className="tick-label">{y}</div>
            </div>
          );
        })}
        <div className="slider-thumb" style={{ left: pct + "%" }}>
          <div className="thumb-inner" />
          <div className="thumb-line" />
        </div>
        <div className="slider-today" style={{ left: ((THESIS.TODAY - min) / (max - min)) * 100 + "%" }}>
          <div className="today-line" />
          <div className="today-label">TODAY</div>
        </div>
      </div>
    </div>
  );
}

// ---------- generic info tooltip ----------
function InfoTip({ label, children, side = "bottom", width = 280 }) {
  return (
    <span className="info-tip" tabIndex={0}>
      {label ? <span className="info-tip-trigger">{label}</span> : null}
      <span className="info-tip-icon" aria-hidden="true">?</span>
      <span className={"info-tip-popup info-tip-" + side} style={{ width }}>
        {children}
      </span>
    </span>
  );
}

// ---------- top chrome ----------
function TopBar({ view, setView, focused, theme, setTheme, settingsOpen, setSettingsOpen }) {
  return (
    <header className="topbar">
      <div className="topbar-left">
        <div className="topbar-mark">
          <svg width="18" height="18" viewBox="0 0 22 22" fill="none"><circle cx="11" cy="11" r="9" stroke="white" strokeWidth="1.5" opacity="0.9"/><circle cx="11" cy="11" r="3" fill="white"/><line x1="11" y1="2" x2="11" y2="5" stroke="white" strokeWidth="1.2" opacity="0.7"/><line x1="11" y1="17" x2="11" y2="20" stroke="white" strokeWidth="1.2" opacity="0.7"/></svg>
        </div>
        <div className="topbar-titles">
          <h1 className="thesis-title">From Social Signals to Pre-Seed Allocation</h1>
          <div className="thesis-sub">Kristian Ratkov · supervised by George Tovstiga · EDHEC MSc Finance</div>
        </div>
      </div>
      <div className="topbar-right">
        <div className="topbar-status" title="All scoring uses only data observable at the slider date T. No future information leaks in.">
          <span className="status-dot ok" /> <span>Lookahead-bias guard</span>
        </div>
        <button
          className={"icon-btn " + (settingsOpen ? "on" : "")}
          onClick={() => setSettingsOpen(o => !o)}
          aria-label="Settings"
          title="Adjust capital, K, allocation rule"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
        </button>
        <button
          className="icon-btn"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label="Toggle theme"
          title={theme === "dark" ? "Switch to light" : "Switch to dark"}
        >
          {theme === "dark" ? (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="4"/><line x1="12" y1="2" x2="12" y2="4"/><line x1="12" y1="20" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="6.34" y2="6.34"/><line x1="17.66" y1="17.66" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="4" y2="12"/><line x1="20" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="6.34" y2="17.66"/><line x1="17.66" y1="6.34" x2="19.07" y2="4.93"/></svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
          )}
        </button>
      </div>
    </header>
  );
}

// ---------- settings popover ----------
function SettingsPopover({ open, onClose, capital, setCapital, K, setK, rule, setRule }) {
  if (!open) return null;
  return (
    <>
      <div className="settings-scrim" onClick={onClose}/>
      <div className="settings-popover">
        <div className="settings-head">
          <span className="kicker">Demo settings</span>
          <button className="icon-btn sm" onClick={onClose} aria-label="Close">×</button>
        </div>
        <div className="settings-body">
          <div className="settings-row">
            <label className="settings-label">
              Capital deployed
              <InfoTip>Total dollars allocated across the K picks. Affects per-founder allocation, not the ranking.</InfoTip>
            </label>
            <div className="seg">
              {[2, 5, 10, 25].map(v => (
                <button key={v} className={capital === v ? "on" : ""} onClick={() => setCapital(v)}>${v}M</button>
              ))}
            </div>
          </div>
          <div className="settings-row">
            <label className="settings-label">
              K (portfolio size)
              <InfoTip>How many founders to back at date T. Smaller K is more concentrated; larger K dilutes precision but reduces variance.</InfoTip>
            </label>
            <div className="seg">
              {[10, 20, 30].map(v => (
                <button key={v} className={K === v ? "on" : ""} onClick={() => setK(v)}>{v}</button>
              ))}
            </div>
          </div>
          <div className="settings-row">
            <label className="settings-label">
              Allocation rule
              <InfoTip>How capital is split. Equal-weight is the safest default; score-weighted concentrates on highest-Σ picks; Kelly-fraction sizes by edge.</InfoTip>
            </label>
            <div className="seg">
              {[
                { id: "equal", label: "equal" },
                { id: "score", label: "score-weighted" },
                { id: "kelly", label: "Kelly-frac" }
              ].map(o => (
                <button key={o.id} className={rule === o.id ? "on" : ""} onClick={() => setRule(o.id)}>{o.label}</button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

// ---------- step indicator (3-minute story arc) ----------
function StepRail({ view, picks, revealed, focusedFounder }) {
  const sliderHasMoved = false; // could track, but visual hint is enough
  const steps = [
    {
      n: 1, label: "Replay",
      hint: view === 1 ? "drag the slider to watch picks reshuffle" : "you watched the framework decide",
      active: view === 1,
      done: view > 1 || revealed
    },
    {
      n: 2, label: "Outcome",
      hint: view === 2 ? "compare precision vs. naïve baselines" : "did the picks emerge?",
      active: view === 2,
      done: view === 3
    },
    {
      n: 3, label: focusedFounder ? "Drill into " + focusedFounder.name : "Founder",
      hint: view === 3 ? "see the KG, signals, and timeline" : (focusedFounder ? "click any row to drill in" : "select a founder"),
      active: view === 3,
      done: false
    }
  ];
  return (
    <div className="step-rail">
      {steps.map(s => (
        <div key={s.n} className={"step-item " + (s.active ? "active " : "") + (s.done ? "done" : "")}>
          <span className="step-num">{s.done ? "✓" : s.n}</span>
          <span className="step-content">
            <span className="step-label">{s.label}</span>{" "}
            <span className="step-hint">— {s.hint}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

// ---------- view nav (also doubles as the step indicator) ----------
function ViewNav({ view, setView, focusedFounder, revealed }) {
  const items = [
    {
      id: 1, label: "Pick",
      hint: view === 1 ? "drag the slider → watch the top-K reshuffle" : "who would we have backed at date T?",
      done: view > 1 || revealed
    },
    {
      id: 2, label: "Score",
      hint: view === 2 ? "how many of the picks emerged within 24 months?" : "how did the picks perform?",
      done: view > 2
    },
    {
      id: 3, label: "Drill in",
      hint: focusedFounder ? (view === 3 ? "why was " + focusedFounder.name + " picked?" : "→ " + focusedFounder.name) : "click a row in Pick to focus a founder",
      done: false
    }
  ];
  return (
    <nav className="view-nav">
      {items.map((it, i) => (
        <button
          key={it.id}
          className={"view-btn " + (view === it.id ? "active " : "") + (it.done ? "done" : "")}
          onClick={() => setView(it.id)}
          disabled={it.id === 3 && !focusedFounder}
        >
          <span className="view-num-wrap">
            <span className="view-num-circle">{it.done ? <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M2 5l2 2 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg> : ("0" + it.id)}</span>
            {i < items.length - 1 && <span className="view-num-connector"/>}
          </span>
          <span className="view-text">
            <span className="view-label">{it.label}</span>
            <span className="view-hint">{it.hint}</span>
          </span>
        </button>
      ))}
    </nav>
  );
}

// ---------- view intro banner ----------
function ViewIntro({ kicker, title, children }) {
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

// ---------- footer ----------
function Footer() {
  return (
    <footer className="footer">
      <div>Working artefact for thesis defence · <span className="mono">2026-07-18</span></div>
      <div className="muted">Code: <span className="mono">github.com/KR2809/the-social-media-vc-thesis</span></div>
      <div className="muted">Frozen <span className="mono">2026-05-31</span> · build <span className="mono">7ad4f9c</span></div>
    </footer>
  );
}

// ---------- episteme caption ----------
function EpistemeBar({ children }) {
  return (
    <div className="episteme">
      <span className="ep-mark">ⓘ</span>
      <span>{children}</span>
    </div>
  );
}

window.Chrome = {
  Avatar, OutcomeChip, ScoreSpark, CIBar, InfoTip,
  DateSlider, TopBar, SettingsPopover, ViewNav, ViewIntro, Footer, EpistemeBar,
  fmtPct, fmtScore, fmtMoney
};
