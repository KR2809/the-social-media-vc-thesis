"use client";

import { InfoTip } from "./InfoTip";

export type AllocationRule = "equal" | "score" | "kelly";

interface Props {
  open: boolean;
  onClose: () => void;
  capital: number;
  setCapital: (v: number) => void;
  K: number;
  setK: (v: number) => void;
  rule: AllocationRule;
  setRule: (v: AllocationRule) => void;
}

export function SettingsPopover({
  open,
  onClose,
  capital,
  setCapital,
  K,
  setK,
  rule,
  setRule,
}: Props) {
  if (!open) return null;
  return (
    <>
      <div className="settings-scrim" onClick={onClose} />
      <div className="settings-popover">
        <div className="settings-head">
          <span className="kicker">Demo settings</span>
          <button className="icon-btn sm" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="settings-body">
          <div className="settings-row">
            <label className="settings-label">
              Capital deployed
              <InfoTip>
                Total dollars allocated across the K picks. Affects per-founder allocation, not the ranking.
              </InfoTip>
            </label>
            <div className="seg">
              {[2, 5, 10, 25].map(v => (
                <button
                  key={v}
                  className={capital === v ? "on" : ""}
                  onClick={() => setCapital(v)}
                >
                  ${v}M
                </button>
              ))}
            </div>
          </div>
          <div className="settings-row">
            <label className="settings-label">
              K (portfolio size)
              <InfoTip>
                How many founders to back at date T. Smaller K is more concentrated; larger K dilutes precision but reduces variance.
              </InfoTip>
            </label>
            <div className="seg">
              {[10, 20, 30].map(v => (
                <button
                  key={v}
                  className={K === v ? "on" : ""}
                  onClick={() => setK(v)}
                >
                  {v}
                </button>
              ))}
            </div>
          </div>
          <div className="settings-row">
            <label className="settings-label">
              Allocation rule
              <InfoTip>
                How capital is split. Equal-weight is the safest default; score-weighted concentrates on highest-Σ picks; Kelly-fraction sizes by edge.
              </InfoTip>
            </label>
            <div className="seg">
              {([
                { id: "equal", label: "equal" },
                { id: "score", label: "score-weighted" },
                { id: "kelly", label: "Kelly-frac" },
              ] as const).map(o => (
                <button
                  key={o.id}
                  className={rule === o.id ? "on" : ""}
                  onClick={() => setRule(o.id)}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
