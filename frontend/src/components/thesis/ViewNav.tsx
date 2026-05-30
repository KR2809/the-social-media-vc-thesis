"use client";

import type { Founder } from "@/lib/thesis";

// Includes 4 (the Knowledge Graph view) for prop compatibility with App,
// though the stepper itself only renders steps 1–3.
type View = 1 | 2 | 3 | 4;

interface Props {
  view: View;
  setView: (v: View) => void;
  focusedFounder: Founder | null;
  revealed: boolean;
}

export function ViewNav({ view, setView, focusedFounder, revealed }: Props) {
  const items = [
    {
      id: 1 as const,
      label: "Pick",
      hint:
        view === 1
          ? "drag the slider → watch the top-K reshuffle"
          : "who would we have backed at date T?",
      done: view > 1 || revealed,
    },
    {
      id: 2 as const,
      label: "Score",
      hint:
        view === 2
          ? "how many of the picks emerged within 24 months?"
          : "how did the picks perform?",
      done: view > 2,
    },
    {
      id: 3 as const,
      label: "Drill in",
      hint: focusedFounder
        ? view === 3
          ? "why was " + focusedFounder.name + " picked?"
          : "→ " + focusedFounder.name
        : "click a row in Pick to focus a founder",
      done: false,
    },
  ];
  return (
    <nav className="view-nav">
      {items.map((it, i) => (
        <button
          key={it.id}
          className={
            "view-btn " +
            (view === it.id ? "active " : "") +
            (it.done ? "done" : "")
          }
          onClick={() => setView(it.id)}
          disabled={it.id === 3 && !focusedFounder}
        >
          <span className="view-num-wrap">
            <span className="view-num-circle">
              {it.done ? (
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                  <path
                    d="M2 5l2 2 4-4"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              ) : (
                "0" + it.id
              )}
            </span>
            {i < items.length - 1 && <span className="view-num-connector" />}
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
