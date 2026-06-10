"use client";

import { useEffect } from "react";
import { hasSignals, type TimelineFounder } from "@/lib/thesis/timeline";

// Founder click-through panel (spec §4, step 3).
// Shows the plain lead-time story + the REAL posts the system saw at the
// moment it flagged them. No-fabrication guard: if a founder has no scored
// signals, say so — never invent posts.

function leadSentence(f: TimelineFounder): string {
  const lead = f.lead_time_months;
  if (lead == null || !f.emergence_date) return "";
  if (lead > 0) {
    return `The system flagged ${f.founder_name.split(" ")[0]} ${lead} months before the launch.`;
  }
  if (lead === 0) return "Flagged the same month as the launch.";
  return "Public history for this founder starts after their launch, so the system could only confirm it afterwards — a limit of the data, shown honestly.";
}

const PLATFORM_LABEL: Record<string, string> = {
  hackernews: "Hacker News",
  twitter: "X / Twitter",
  reddit: "Reddit",
  producthunt: "Product Hunt",
  youtube: "YouTube",
};

export function FounderDetail({
  founder,
  onClose,
}: {
  founder: TimelineFounder;
  onClose: () => void;
}) {
  // Esc closes; lock body scroll while open.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  return (
    <div className="lp-fd-overlay" onClick={onClose} role="presentation">
      <aside
        className="lp-fd"
        role="dialog"
        aria-label={`${founder.founder_name} details`}
        onClick={(e) => e.stopPropagation()}
      >
        <button className="lp-fd-close" onClick={onClose} aria-label="Close">
          ×
        </button>
        <h3 className="lp-fd-name">{founder.founder_name}</h3>
        {founder.venture && <p className="lp-fd-venture">{founder.venture}</p>}

        <div className="lp-fd-dates mono">
          {founder.first_pickup_date && (
            <span>
              <span className="lp-fd-k">flagged</span>{" "}
              {founder.first_pickup_date.slice(0, 7)}
            </span>
          )}
          {founder.emergence_date && (
            <span>
              <span className="lp-fd-k">launched</span>{" "}
              {founder.emergence_date.slice(0, 7)}
            </span>
          )}
        </div>

        <p className="lp-fd-lead">{leadSentence(founder)}</p>

        <h4 className="lp-fd-sub">What the system saw when it flagged them</h4>
        {hasSignals(founder) ? (
          <ul className="lp-fd-signals">
            {founder.top_signals_at_pickup.slice(0, 4).map((s) => (
              <li key={s.signal_id} className="lp-fd-signal">
                <span className="lp-fd-platform mono">
                  {PLATFORM_LABEL[s.platform] ?? s.platform}
                </span>
                <span className="lp-fd-text">
                  {s.text ? `“${s.text}”` : "(post without text content)"}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="lp-fd-nodata">
            Limited public data for this founder — the system flagged them on
            volume and timing patterns, and there are no stored example posts
            to show. We don&apos;t invent any.
          </p>
        )}
      </aside>
    </div>
  );
}
