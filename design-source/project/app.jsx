/* Root app — orchestrates state, view switching, slider. */

const { useState: useAppState, useEffect: useAppEffect, useMemo: useAppMemo } = React;
const { DateSlider, TopBar, SettingsPopover, ViewNav, Footer } = window.Chrome;

function App() {
  // Slider domain: months since 2014-01.
  const MIN = 0;
  const MAX = THESIS.months("2026-05");
  // Default to demo scenario: 2022-Q1.
  const [t, setT] = useAppState(THESIS.months("2022-Q1"));
  const [K, setK] = useAppState(20);
  const [capital, setCapital] = useAppState(5);
  const [rule, setRule] = useAppState("equal");
  const [view, setView] = useAppState(1);
  const [focusedId, setFocusedId] = useAppState("marclou");
  const [revealed, setRevealed] = useAppState(false);
  const [settingsOpen, setSettingsOpen] = useAppState(false);
  const [theme, setTheme] = useAppState(() => {
    const stored = localStorage.getItem("thesis-theme");
    if (stored) return stored;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  useAppEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("thesis-theme", theme);
  }, [theme]);

  // Keyboard: 1/2/3 to switch views, arrows to nudge slider
  useAppEffect(() => {
    function onKey(e) {
      if (e.target && /^(INPUT|TEXTAREA)$/.test(e.target.tagName)) return;
      if (e.key === "Escape") setSettingsOpen(false);
      else if (e.key === "1") setView(1);
      else if (e.key === "2") setView(2);
      else if (e.key === "3" && focusedId) setView(3);
      else if (e.key === "ArrowLeft") setT(v => Math.max(MIN, v - 3));
      else if (e.key === "ArrowRight") setT(v => Math.min(MAX, v + 3));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [focusedId, MAX]);

  const picks = useAppMemo(() => THESIS.rankAt(t, K), [t, K]);
  const focusedFounder = focusedId ? THESIS.FOUNDERS_RAW.find(f => f.id === focusedId) : null;

  return (
    <div className="app">
      <TopBar
        view={view} setView={setView}
        theme={theme} setTheme={setTheme}
        settingsOpen={settingsOpen} setSettingsOpen={setSettingsOpen}
      />
      <DateSlider value={t} onChange={setT} min={MIN} max={MAX}/>
      <ViewNav view={view} setView={setView} focusedFounder={focusedFounder} revealed={revealed}/>
      <SettingsPopover
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        capital={capital} setCapital={setCapital}
        K={K} setK={setK}
        rule={rule} setRule={setRule}
      />
      <div className="app-body">
        {view === 1 && (
          <window.View1Replay
            t={t} K={K} capital={capital}
            focusedId={focusedId} setFocused={setFocusedId}
            gotoView={setView}
            revealed={revealed} setRevealed={setRevealed}
          />
        )}
        {view === 2 && (
          <window.View2Outcome
            t={t} K={K} picks={picks}
            onFocusFounder={setFocusedId}
            gotoView={setView}
          />
        )}
        {view === 3 && (
          <window.View3Founder
            founderId={focusedId} t={t} gotoView={setView}
          />
        )}
      </div>
      <Footer/>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
