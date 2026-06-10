"use client";

import { useReveal } from "./useInView";

// §3 THE IDEA — "founders leave a trail" (spec §3).
// Three plain-English cards. These map to the thesis's signal families
// (content pattern / expressed intention / network behaviour) but are NEVER
// labelled with taxonomy codes here (HARD RULE).

const CARDS = [
  {
    title: "They build in public",
    body: "Months before launching anything official, future founders are already shipping — side projects, progress updates, little experiments, lessons learned.",
    icon: "🛠",
  },
  {
    title: "They say it out loud",
    body: "They talk about what they want to build, share goals, ask for feedback, and start looking for collaborators — long before there's a company.",
    icon: "📣",
  },
  {
    title: "They pull people in",
    body: "Other builders, early users and experienced operators start gathering around them — before they have any title or status to offer.",
    icon: "🧲",
  },
];

export function SectionIdea() {
  const [ref, revealCls] = useReveal<HTMLElement>();
  return (
    <section
      id="idea"
      ref={ref}
      className={"lp-section lp-idea " + revealCls}
      aria-label="The idea"
    >
      <p className="lp-kicker mono">The idea</p>
      <h2 className="lp-h2">Founders leave a trail before they launch.</h2>
      <p className="lp-body">
        The system reads three kinds of public behaviour and scores how
        strongly someone looks like a founder-in-the-making:
      </p>
      <div className="lp-idea-cards">
        {CARDS.map((c, i) => (
          <div
            key={c.title}
            className="lp-idea-card"
            style={{ transitionDelay: `${i * 120}ms` }}
          >
            <span className="lp-idea-icon" aria-hidden>{c.icon}</span>
            <h3 className="lp-idea-title">{c.title}</h3>
            <p className="lp-idea-body">{c.body}</p>
          </div>
        ))}
      </div>
      <p className="lp-idea-note">
        Every post is read and scored automatically — about thirty different
        little signals, combined into one score per person.
      </p>
    </section>
  );
}
