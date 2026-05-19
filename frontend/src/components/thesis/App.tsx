"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getThesisSource, syntheticSource } from "@/lib/thesis";
import type { DataSource } from "@/lib/thesis";
import { ThesisProvider } from "@/lib/thesis/context";
import { TopBar } from "./TopBar";
import { DateSlider } from "./DateSlider";
import { ViewNav } from "./ViewNav";
import { SettingsPopover, type AllocationRule } from "./SettingsPopover";
import { Footer } from "./primitives";
import { View1Replay } from "./View1Replay";
import { View2Outcome } from "./View2Outcome";
import { View3Founder } from "./View3Founder";

type Theme = "light" | "dark";
type View = 1 | 2 | 3;

const MIN = 0;
// Month-parsing is data-independent, so we read it off the synthetic source
// at module load — both synthetic and hybrid use the same parser.
const MAX = syntheticSource.months("2026-05")!;
const DEFAULT_T = syntheticSource.months("2022-Q1")!;

function parseT(s: string | null): number {
  const n = s == null ? DEFAULT_T : parseInt(s, 10);
  if (Number.isNaN(n)) return DEFAULT_T;
  return Math.max(MIN, Math.min(MAX, n));
}
function parseView(s: string | null): View {
  if (s === "2") return 2;
  if (s === "3") return 3;
  return 1;
}
function parseK(s: string | null): number {
  const n = s == null ? 20 : parseInt(s, 10);
  return [10, 20, 30].includes(n) ? n : 20;
}
function parseCapital(s: string | null): number {
  const n = s == null ? 5 : parseInt(s, 10);
  return [2, 5, 10, 25].includes(n) ? n : 5;
}
function parseRule(s: string | null): AllocationRule {
  return s === "score" || s === "kelly" ? s : "equal";
}

export function App() {
  const router = useRouter();
  const params = useSearchParams();

  // Resolve the active DataSource (real → hybrid, fallback → synthetic).
  // Synthetic is rendered first so SSR + initial hydration stay deterministic;
  // the real source swaps in once /api/cohort + /api/timeline-bounds resolve.
  const [thesis, setThesis] = useState<DataSource>(syntheticSource);
  useEffect(() => {
    let cancelled = false;
    getThesisSource().then((src) => {
      if (!cancelled) setThesis(src);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const [t, setTState] = useState(() => parseT(params.get("t")));
  const [view, setViewState] = useState<View>(() => parseView(params.get("view")));
  const [K, setKState] = useState(() => parseK(params.get("K")));
  const [capital, setCapitalState] = useState(() => parseCapital(params.get("capital")));
  const [rule, setRuleState] = useState<AllocationRule>(() => parseRule(params.get("rule")));
  const [focusedId, setFocusedIdState] = useState<string>(
    () => params.get("f") || "marclou",
  );
  const [revealed, setRevealed] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  // Theme: SSR-safe. Mounted=false until the first effect, then resolve from
  // localStorage / system preference. The TopBar reads `mounted` to skip
  // rendering the theme-dependent icon during SSR.
  const [theme, setTheme] = useState<Theme>("light");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("thesis-theme");
    const resolved: Theme =
      stored === "dark" || stored === "light"
        ? stored
        : window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
    setTheme(resolved);
    setMounted(true);
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("thesis-theme", theme);
  }, [theme]);

  // URL sync — replace, don't push, so back button still works naturally.
  const syncUrl = useCallback(
    (next: Partial<{ t: number; view: View; K: number; capital: number; rule: AllocationRule; f: string }>) => {
      const q = new URLSearchParams(params.toString());
      const merged = {
        t: next.t ?? t,
        view: next.view ?? view,
        K: next.K ?? K,
        capital: next.capital ?? capital,
        rule: next.rule ?? rule,
        f: next.f ?? focusedId,
      };
      q.set("t", String(merged.t));
      q.set("view", String(merged.view));
      q.set("K", String(merged.K));
      q.set("capital", String(merged.capital));
      q.set("rule", merged.rule);
      q.set("f", merged.f);
      router.replace(`/?${q.toString()}`, { scroll: false });
    },
    [router, params, t, view, K, capital, rule, focusedId],
  );

  const setT = useCallback(
    (v: number) => {
      setTState(v);
      syncUrl({ t: v });
    },
    [syncUrl],
  );
  const setView = useCallback(
    (v: View) => {
      setViewState(v);
      syncUrl({ view: v });
    },
    [syncUrl],
  );
  const setK = useCallback(
    (v: number) => {
      setKState(v);
      syncUrl({ K: v });
    },
    [syncUrl],
  );
  const setCapital = useCallback(
    (v: number) => {
      setCapitalState(v);
      syncUrl({ capital: v });
    },
    [syncUrl],
  );
  const setRule = useCallback(
    (v: AllocationRule) => {
      setRuleState(v);
      syncUrl({ rule: v });
    },
    [syncUrl],
  );
  const setFocusedId = useCallback(
    (v: string) => {
      setFocusedIdState(v);
      syncUrl({ f: v });
    },
    [syncUrl],
  );

  // Keyboard shortcuts.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA)$/.test(target.tagName)) return;
      if (e.key === "Escape") setSettingsOpen(false);
      else if (e.key === "1") setView(1);
      else if (e.key === "2") setView(2);
      else if (e.key === "3" && focusedId) setView(3);
      else if (e.key === "ArrowLeft") setT(Math.max(MIN, t - 3));
      else if (e.key === "ArrowRight") setT(Math.min(MAX, t + 3));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [focusedId, setView, setT, t]);

  const focusedFounder = useMemo(
    () => (focusedId ? thesis.founders().find(f => f.id === focusedId) ?? null : null),
    [focusedId, thesis],
  );

  const picks = useMemo(() => thesis.rankAt(t, K), [t, K, thesis]);

  return (
    <ThesisProvider value={thesis}>
    <div className="app">
      <TopBar
        theme={theme}
        setTheme={setTheme}
        settingsOpen={settingsOpen}
        setSettingsOpen={setSettingsOpen}
        mounted={mounted}
      />
      <DateSlider value={t} onChange={setT} min={MIN} max={MAX} />
      <ViewNav
        view={view}
        setView={setView}
        focusedFounder={focusedFounder}
        revealed={revealed}
      />
      <SettingsPopover
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        capital={capital}
        setCapital={setCapital}
        K={K}
        setK={setK}
        rule={rule}
        setRule={setRule}
      />
      <div className="app-body">
        {view === 1 && (
          <View1Replay
            t={t}
            K={K}
            capital={capital}
            focusedId={focusedId}
            setFocused={setFocusedId}
            gotoView={setView}
            revealed={revealed}
            setRevealed={setRevealed}
          />
        )}
        {view === 2 && (
          <View2Outcome
            t={t}
            K={K}
            picks={picks}
            onFocusFounder={setFocusedId}
            gotoView={setView}
          />
        )}
        {view === 3 && (
          <View3Founder
            founderId={focusedId}
            t={t}
            gotoView={setView}
          />
        )}
      </div>
      <Footer />
    </div>
    </ThesisProvider>
  );
}
