"use client";

import type { Dispatch, SetStateAction } from "react";
import { useThesis } from "@/lib/thesis/context";

type Theme = "light" | "dark";

interface Props {
  theme: Theme;
  setTheme: Dispatch<SetStateAction<Theme>>;
  settingsOpen: boolean;
  setSettingsOpen: Dispatch<SetStateAction<boolean>>;
  mounted: boolean;
  onOpenGuide: () => void;
}

export function TopBar({ theme, setTheme, settingsOpen, setSettingsOpen, mounted, onOpenGuide }: Props) {
  const thesis = useThesis();
  const cov = thesis.coverage();
  return (
    <header className="topbar">
      <div className="topbar-left">
        <div className="topbar-mark">
          <svg width="18" height="18" viewBox="0 0 22 22" fill="none">
            <circle cx="11" cy="11" r="9" stroke="white" strokeWidth="1.5" opacity="0.9" />
            <circle cx="11" cy="11" r="3" fill="white" />
            <line x1="11" y1="2" x2="11" y2="5" stroke="white" strokeWidth="1.2" opacity="0.7" />
            <line x1="11" y1="17" x2="11" y2="20" stroke="white" strokeWidth="1.2" opacity="0.7" />
          </svg>
        </div>
        <div className="topbar-titles">
          <h1 className="thesis-title">From Social Signals to Pre-Seed Allocation</h1>
          <div className="thesis-sub">
            Kristian Ratkov · supervised by George Tovstiga · EDHEC MSc Finance
          </div>
        </div>
      </div>
      <div className="topbar-right">
        <div
          className="topbar-status"
          data-testid="coverage-pill"
          title={`Cohort: ${cov.totalFounders} founders. ${cov.foundersWithSignals} have collected + scored signals (${cov.scoredEvents} events total). The remaining founders render with synthetic curves until backfill catches up.`}
        >
          <span className={"status-dot " + (cov.foundersWithSignals > 0 ? "ok" : "mu")} />
          <span className="mono">
            {cov.foundersWithSignals}/{cov.totalFounders}
          </span>
          <span> · {cov.scoredEvents} events</span>
        </div>
        <div
          className="topbar-status"
          title="All scoring uses only data observable at the slider date T. No future information leaks in."
        >
          <span className="status-dot ok" /> <span>Lookahead-bias guard</span>
        </div>
        <button
          className="icon-btn"
          onClick={onOpenGuide}
          aria-label="Open walkthrough"
          title="What am I looking at? — open the walkthrough"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <circle cx="12" cy="12" r="9" />
            <path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 2.5-3 2.5" strokeLinecap="round" />
            <line x1="12" y1="17" x2="12" y2="17.01" strokeLinecap="round" />
          </svg>
        </button>
        <button
          className={"icon-btn " + (settingsOpen ? "on" : "")}
          onClick={() => setSettingsOpen(o => !o)}
          aria-label="Settings"
          title="Adjust capital, K, allocation rule"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </button>
        <button
          className="icon-btn"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label="Toggle theme"
          title={
            mounted ? (theme === "dark" ? "Switch to light" : "Switch to dark") : "Toggle theme"
          }
          suppressHydrationWarning
        >
          {/* Render a placeholder while mounted=false to avoid hydration mismatch. */}
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" suppressHydrationWarning>
            {mounted && theme === "dark" ? (
              <>
                <circle cx="12" cy="12" r="4" />
                <line x1="12" y1="2" x2="12" y2="4" />
                <line x1="12" y1="20" x2="12" y2="22" />
                <line x1="4.93" y1="4.93" x2="6.34" y2="6.34" />
                <line x1="17.66" y1="17.66" x2="19.07" y2="19.07" />
                <line x1="2" y1="12" x2="4" y2="12" />
                <line x1="20" y1="12" x2="22" y2="12" />
                <line x1="4.93" y1="19.07" x2="6.34" y2="17.66" />
                <line x1="17.66" y1="6.34" x2="19.07" y2="4.93" />
              </>
            ) : (
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
            )}
          </svg>
        </button>
      </div>
    </header>
  );
}
