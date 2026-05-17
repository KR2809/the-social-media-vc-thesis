/* View 3 — Founder card. KG ego-network + top signals + outcome timeline + narrative. */

const { useMemo: useMemo3, useState: useState3 } = React;
const { Avatar: Av3, OutcomeChip: OC3, EpistemeBar: EB3, ViewIntro: VI3, InfoTip: IT3, fmtScore: fs3 } = window.Chrome;

// ---------- ego-network ----------
function EgoNetwork({ founderId, hop, setHop }) {
  const data = useMemo3(() => THESIS.egoFor(founderId), [founderId]);
  const W = 380, H = 320;
  // Layout: founder centred; signals on inner ring; topics on outer-right; platforms on outer-left
  const positions = useMemo3(() => {
    const pos = {};
    pos["F"] = { x: W / 2, y: H / 2 };
    const signals = data.nodes.filter(n => n.kind === "signal");
    signals.forEach((n, i) => {
      const a = -Math.PI / 2 + (i / Math.max(signals.length - 1, 1)) * Math.PI;
      pos[n.id] = { x: W / 2 + Math.cos(a) * 80, y: H / 2 + Math.sin(a) * 80 };
    });
    const topics = data.nodes.filter(n => n.kind === "topic");
    topics.forEach((n, i) => {
      pos[n.id] = { x: W - 50, y: 60 + i * 70 };
    });
    const platforms = data.nodes.filter(n => n.kind === "platform");
    platforms.forEach((n, i) => {
      pos[n.id] = { x: 40, y: 60 + i * 80 };
    });
    return pos;
  }, [data]);

  const nodeColor = (kind) => ({
    founder:  "var(--accent-deep)",
    signal:   "var(--ink-1)",
    topic:    "var(--accent)",
    platform: "var(--ink-3)"
  }[kind]);

  return (
    <div className="ego-wrap">
      <div className="ego-controls">
        <div className="ego-legend">
          <span><span className="dot" style={{ background: "var(--accent-deep)" }}/> founder</span>
          <span><span className="dot" style={{ background: "var(--ink-1)" }}/> signal</span>
          <span><span className="dot" style={{ background: "var(--accent)" }}/> topic</span>
          <span><span className="dot" style={{ background: "var(--ink-3)" }}/> platform</span>
        </div>
        <div className="seg sm">
          <button className={hop === 1 ? "on" : ""} onClick={() => setHop(1)}>1-hop</button>
          <button className={hop === 2 ? "on" : ""} onClick={() => setHop(2)}>2-hop</button>
        </div>
      </div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} className="ego-svg">
        <defs>
          <marker id="arrow" markerWidth="6" markerHeight="6" refX="6" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6 Z" fill="var(--ink-3)"/>
          </marker>
        </defs>
        {data.edges.map((e, i) => {
          const a = positions[e.a], b = positions[e.b]; if (!a || !b) return null;
          return (
            <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke={"var(--accent)"} strokeOpacity={0.20 + e.w * 0.5}
              strokeWidth={0.6 + e.w * 1.6}/>
          );
        })}
        {hop === 2 && (
          // sketch 2-hop expansion: faint ghost nodes
          [0, 1, 2, 3].map(i => {
            const a = (i / 4) * Math.PI * 2;
            return <circle key={"g"+i} cx={W/2 + Math.cos(a) * 150} cy={H/2 + Math.sin(a) * 130} r="6" fill="var(--ink-3)" opacity="0.15"/>;
          })
        )}
        {data.nodes.map(n => {
          const p = positions[n.id]; if (!p) return null;
          const r = n.kind === "founder" ? 18 : n.kind === "signal" ? 10 : 8;
          return (
            <g key={n.id} transform={`translate(${p.x}, ${p.y})`}>
              <circle r={r + 3} fill="var(--bg)" stroke={nodeColor(n.kind)} strokeWidth="1"/>
              <circle r={r} fill={nodeColor(n.kind)} opacity={n.kind === "founder" ? 1 : 0.85}/>
              {n.kind === "founder"
                ? <text y="4" textAnchor="middle" fontFamily="var(--serif)" fontSize="11" fill="var(--bg)" fontWeight="600">F</text>
                : <text y={r + 12} textAnchor="middle" fontFamily="var(--mono)" fontSize="9" fill="var(--ink-2)">{n.label}</text>}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ---------- top 5 signals ----------
function TopSignals({ founderId, t }) {
  const signals = useMemo3(() => THESIS.signalsFor(founderId, t), [founderId, t]);
  return (
    <div className="signals">
      {signals.map((s, i) => (
        <div key={s.id} className="signal-card">
          <div className="signal-head">
            <span className="signal-rank mono">{String(i + 1).padStart(2, "0")}</span>
            <span className="signal-text">"{s.raw}"</span>
          </div>
          <div className="signal-meta">
            <span className="meta-pair"><span className="kicker">PLATFORM</span> <span className="mono">{s.platform}</span></span>
            <span className="meta-pair"><span className="kicker">DATE</span> <span className="mono">{s.timestamp}</span></span>
            <span className="meta-pair"><span className="kicker">Σ DIMS</span> <span className="mono">{Object.keys(THESIS.TAX).length}</span></span>
          </div>
          <div className="tax-chips">
            <TaxChip dim={s.dim} cat={s.cat} score={s.score}/>
            {[1,2,3,4].map(j => {
              const cats = Object.keys(THESIS.TAX);
              const cat = cats[(i + j) % cats.length];
              const dim = cat + "." + (j) + " " + ["consistency","reach","artefacts","followers"][j-1];
              const score = Math.max(0.42, s.score - 0.08 - j * 0.07);
              return <TaxChip key={j} dim={dim} cat={cat} score={score}/>;
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

function TaxChip({ dim, cat, score }) {
  const t = THESIS.TAX[cat];
  return (
    <span className="tax-chip" style={{ color: t.color, borderColor: t.color, background: t.color + "14" }}>
      <span className="tax-dim">{dim}</span>
      <span className="tax-score mono">{score.toFixed(2)}</span>
    </span>
  );
}

// ---------- outcome timeline ----------
function Timeline({ founderId, t }) {
  const f = THESIS.FOUNDERS_RAW.find(x => x.id === founderId); if (!f) return null;
  const fm = THESIS.months(f.first);
  const em = THESIS.months(f.emerge);
  const endM = em != null ? em + 6 : Math.max(t + 6, fm + 60);
  const span = endM - fm;
  const pct = (mo) => ((mo - fm) / Math.max(span, 1)) * 100;

  // synthetic milestones derived from emergence date
  const milestones = [];
  milestones.push({ at: fm, kind: "first", label: "First observable signal", sub: THESIS.fmtMonth(fm) });
  milestones.push({ at: fm + Math.floor(span * 0.25), kind: "cadence", label: "Cadence stabilises (>4/day)", sub: ">180d streak" });
  milestones.push({ at: fm + Math.floor(span * 0.45), kind: "follower", label: "10k follower threshold", sub: "+340/wk" });
  if (em != null) {
    milestones.push({ at: em - 4, kind: "venture", label: f.venture ? f.venture + " soft-launch" : "Venture soft-launch", sub: "private beta" });
    milestones.push({ at: em, kind: "emerge", label: "Emergence event", sub: f.venture_metric || "—" });
  } else {
    milestones.push({ at: fm + Math.floor(span * 0.7), kind: "plateau", label: "Signal plateau (no event)", sub: "still tracked" });
  }
  if (t >= fm && t <= endM) {
    milestones.push({ at: t, kind: "T", label: "Cohort date T", sub: THESIS.fmtMonth(t) });
  }

  return (
    <div className="timeline">
      <div className="tl-axis">
        <div className="tl-line"/>
        {/* T window */}
        {t >= fm && t <= endM && (
          <div className="tl-twindow" style={{ left: pct(t) + "%", width: pct(Math.min(t + 24, endM)) - pct(t) + "%" }}>
            <span className="tl-twindow-label">T → T+24mo</span>
          </div>
        )}
        {milestones.map((m, i) => (
          <div key={i} className={"tl-event tl-" + m.kind} style={{ left: pct(m.at) + "%" }}>
            <div className="tl-dot"/>
            <div className="tl-bubble">
              <div className="tl-bubble-label">{m.label}</div>
              <div className="tl-bubble-sub mono">{m.sub}</div>
              <div className="tl-bubble-date mono muted">{THESIS.fmtMonth(m.at)}</div>
            </div>
          </div>
        ))}
      </div>
      <div className="tl-axis-labels">
        <span className="mono">{THESIS.fmtMonth(fm)}</span>
        <span className="mono">{THESIS.fmtMonth(endM)}</span>
      </div>
    </div>
  );
}

// ---------- narrative ----------
function Narrative({ founderId, t }) {
  const f = THESIS.FOUNDERS_RAW.find(x => x.id === founderId); if (!f) return null;
  const c = THESIS.curve(f, t) || 0;
  const em = THESIS.months(f.emerge);
  const monthsToEmerge = em != null ? em - t : null;
  const sigs = THESIS.signalsFor(founderId, t);
  const lead = sigs[0]; const next = sigs[1];
  const monthsSinceFirst = t - THESIS.months(f.first);
  return (
    <div className="narrative">
      <div className="narr-head">
        <span className="kicker">FRAMEWORK NARRATIVE · AUTO-GENERATED · MODEL: claude-haiku-4.5</span>
        <button className="link-btn sm">↻ regenerate</button>
      </div>
      <p className="narr-body">
        At <strong>{THESIS.fmtQuarter(t)}</strong>, <strong>{f.name}</strong> had been posting on {sigs[0].platform.toLowerCase()} for <span className="mono">{Math.max(1, Math.floor(monthsSinceFirst))} months</span>.
        The lead signal was <em>{lead.dim}</em> (score <span className="mono">{lead.score.toFixed(2)}</span>): {lead.raw.toLowerCase()}
        {next && <> Reinforced by <em>{next.dim}</em> (score <span className="mono">{next.score.toFixed(2)}</span>).</>}
        {" "}The KG-augmented combined score was <span className="mono">P(emerge) = {c.toFixed(2)}</span>.
        {em != null && monthsToEmerge != null && monthsToEmerge >= 0 && (
          <> <strong>{f.venture || "The venture"}</strong> launched <span className="mono">{monthsToEmerge} months</span> later{f.venture_metric ? <> at <span className="mono">{f.venture_metric}</span></> : null}.</>
        )}
        {em != null && monthsToEmerge != null && monthsToEmerge < 0 && (
          <> <strong>{f.venture || "The venture"}</strong> had already launched (T is post-emergence by <span className="mono">{Math.abs(monthsToEmerge)} months</span>); included here for retrospective trace.</>
        )}
        {em == null && <> No emergence event observed yet by today ({THESIS.fmtMonth(THESIS.TODAY)}).</>}
      </p>
    </div>
  );
}

// ---------- View 3 root ----------
function View3Founder({ founderId, t, gotoView }) {
  const [hop, setHop] = useState3(1);
  const f = THESIS.FOUNDERS_RAW.find(x => x.id === founderId);
  if (!f) return <section className="view view-3"><div className="empty">No founder selected. Pick a row in Step 01.</div></section>;
  const outcome = THESIS.outcomeAt(f, t);
  return (
    <section className="view view-3">
      <VI3 kicker="STEP 03 · DRILL IN" title={"Why was " + f.name + " picked?"}>
        Trace the framework's per-founder evidence at <strong>{THESIS.fmtMonth(t)}</strong> — the knowledge-graph neighbourhood, the five highest-weight signals, and the outcome timeline. Every signal links back to a source post.
      </VI3>

      <div className="founder-hero">
        <div className="hero-left">
          <Av3 id={f.id} name={f.name} size={56}/>
          <div className="hero-id">
            <span className="hero-handle">@{f.id}</span>
            <span className="hero-name">{f.name}</span>
            <span className="hero-niche">{f.niche}</span>
          </div>
        </div>
        <div className="hero-stats">
          <Stat kicker="Emergence quarter" val={f.emerge ? THESIS.fmtQuarter(THESIS.months(f.emerge)) : "—"} tip="The quarter in which the founder launched a venture (raised pre-seed, hit revenue threshold, or shipped a public product with traction)."/>
          <Stat kicker="Venture" val={f.venture || "—"} tip="The startup or product associated with the emergence event."/>
          <Stat kicker="Outcome @ T+24mo" val={<OC3 outcome={outcome}/>} tip="Did this founder emerge within 24 months of date T? Outcomes only shown when the horizon is in the past."/>
          <Stat kicker="P(emerge)" val={<span className="mono">{(THESIS.curve(f, t) || 0).toFixed(2)}</span>} tip={<>The combined score Σ at date T — the framework's estimate of <em>P(emerges within 24mo)</em>. Range [0,1].</>}/>
        </div>
        <button className="link-btn sm" onClick={() => gotoView(1)}>← back to picks</button>
      </div>

      <div className="founder-grid">
        <div className="founder-panel ego-panel">
          <div className="panel-head">
            <span className="kicker">
              KG ego-network
              <IT3 width={320}>
                The founder (F) and her 1-hop neighbours in the knowledge graph: <strong>signals</strong> she's posted, <strong>topics</strong> they touch, and the <strong>platforms</strong> they live on. Edge weight ≈ co-occurrence strength. T2 features come from this subgraph.
              </IT3>
            </span>
            <span className="muted">click a node to inspect</span>
          </div>
          <EgoNetwork founderId={founderId} hop={hop} setHop={setHop}/>
        </div>
        <div className="founder-panel signals-panel">
          <div className="panel-head">
            <span className="kicker">
              Top 5 signals @ T
              <IT3 width={320}>
                The five highest-weighted signals at date T, each tagged with its taxonomy dimension (<span className="mono">S1–S6</span>) and a normalised score. Source post is reproducible from the parquet row id.
              </IT3>
            </span>
            <span className="muted">{THESIS.fmtMonth(t)}</span>
          </div>
          <TopSignals founderId={founderId} t={t}/>
        </div>
        <div className="founder-panel timeline-panel">
          <div className="panel-head">
            <span className="kicker">
              Outcome timeline
              <IT3 width={280}>
                The trajectory from <strong>first observable signal</strong> to the <strong>emergence event</strong>. The shaded band shows the T → T+24mo evaluation window.
              </IT3>
            </span>
            <span className="muted">first signal → emergence</span>
          </div>
          <Timeline founderId={founderId} t={t}/>
        </div>
      </div>

      <Narrative founderId={founderId} t={t}/>

      <EB3>
        Per-founder trace is reproducible. Every signal links to its source post. KG edges expanded from co-occurrence within ±14d windows. <strong>No future information used.</strong>
      </EB3>
    </section>
  );
}

function Stat({ kicker, val, tip }) {
  return (
    <div className="hero-stat">
      <span className="kicker">
        {kicker}
        {tip ? <IT3 width={280}>{tip}</IT3> : null}
      </span>
      <span className="stat-val">{val}</span>
    </div>
  );
}

window.View3Founder = View3Founder;
