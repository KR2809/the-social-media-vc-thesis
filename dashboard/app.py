"""Streamlit MVP dashboard for the BBA thesis.

4 pages: thesis claim, methodology, cohort status, roadmap.
Deployable to Streamlit Community Cloud free tier.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

EDHEC_BLUE = "#1F4E79"
GITHUB_URL = "github.com/KR2809/the-social-media-vc-thesis"
DATA_DIR = Path(__file__).parent / "data"
# Repo-level processed outputs from `pipeline.py`. Resolved at runtime so
# the dashboard works whether invoked from repo root or dashboard/.
PROCESSED_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"


# ---------- data loaders ----------

@st.cache_data
def load_cohort() -> dict:
    with (DATA_DIR / "cohort_status.json").open() as f:
        return json.load(f)


@st.cache_data
def load_roadmap() -> dict:
    with (DATA_DIR / "roadmap.json").open() as f:
        return json.load(f)


# ---------- chrome ----------

def inject_css() -> None:
    st.markdown(
        f"""
        <style>
          h1, h2, h3 {{
            font-family: Georgia, "Times New Roman", serif;
            color: {EDHEC_BLUE};
          }}
          .claim-quote {{
            border-left: 4px solid {EDHEC_BLUE};
            padding: 1rem 1.25rem;
            background: #f6f9fc;
            font-size: 1.15rem;
            font-style: italic;
            font-family: Georgia, "Times New Roman", serif;
            line-height: 1.5;
            margin: 0.5rem 0 1.25rem 0;
          }}
          .diff-card {{
            border: 1px solid #e1e4e8;
            border-top: 3px solid {EDHEC_BLUE};
            padding: 0.85rem;
            border-radius: 4px;
            background: #fff;
            height: 100%;
          }}
          .footer {{
            border-top: 1px solid #e1e4e8;
            padding-top: 0.75rem;
            margin-top: 2.5rem;
            color: #6a737d;
            font-size: 0.85rem;
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def header() -> None:
    st.markdown(
        "<h1 style='margin-bottom:0.1rem'>From Social Signals to Pre-Seed Allocation</h1>"
        "<div style='color:#555; font-size:1.05rem; font-style:italic; "
        "margin-bottom:0.4rem'>A Systematic Framework for Data-Driven Venture "
        "Capital Inspired by QuantumLight Capital</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='color:#444; margin-bottom:1.25rem'>"
        "A BBA thesis by Kristian Ratkov · EDHEC International BBA · 2025-26 · "
        "Supervisor: Prof. George Tovstiga"
        "</div>",
        unsafe_allow_html=True,
    )


def footer() -> None:
    build_ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    st.markdown(
        f"<div class='footer'>Working artefact for thesis defence Jul 18, 2026. "
        f"Code: {GITHUB_URL}. Last updated: {build_ts}.</div>",
        unsafe_allow_html=True,
    )


# ---------- pages ----------

def page_claim() -> None:
    st.subheader("The claim")
    st.markdown(
        "<div class='claim-quote'>"
        "Observable, multi-platform, public behavioural signals — structured "
        "as a knowledge graph — can be combined into a systematic pre-seed "
        "allocation framework. QuantumLight Capital ($250M, Series B/C) runs "
        "this approach with proprietary operational data; we test the same "
        "principles at pre-seed using only free public social signals."
        "</div>",
        unsafe_allow_html=True,
    )
    st.caption("Paraphrased from the locked thesis title and COMPREHENSIVE_PLAN §1.")

    st.subheader("The research question")
    st.markdown(
        "<div class='claim-quote'>"
        "Can a two-tier framework — Tier 1 topic-momentum detection plus "
        "Tier 2 founder-emergence prediction from public social signals — "
        "produce a defensible pre-seed allocation recommendation that beats "
        "naïve baselines under retrospective backtest?"
        "</div>",
        unsafe_allow_html=True,
    )
    st.caption("Reframed per DECISION_LOG iter-4 (Social-Signal Fund pivot).")

    st.subheader("Five differentiators")
    diffs = [
        ("Individual-level", "Not company-level. The unit of analysis is the person before the venture."),
        ("Pre-launch", "Not post-founding. Signals are read in the window before a formal venture exists."),
        ("Pre-seed VC framing", "QuantumLight at Series B/C with proprietary data → us at pre-seed with public signals."),
        ("Multi-signal integration", "Multiple platforms, not just X. YouTube, Reddit, HN, PH, GH, Substack, GTrends."),
        ("Knowledge-graph methodology", "Relational structure, not flat features. Topics, people, projects, time."),
    ]
    cols = st.columns(5)
    for col, (title, body) in zip(cols, diffs, strict=False):
        with col:
            st.markdown(
                f"<div class='diff-card'><strong>{title}</strong><br>"
                f"<span style='color:#444; font-size:0.9rem'>{body}</span></div>",
                unsafe_allow_html=True,
            )

    st.subheader("How this differs from existing research")
    st.markdown(
        "**Taeuscher & Antretter (2019)** predict venture *survival* post-founding from "
        "Twitter signals. We predict pre-emergence individual signals — the question is who "
        "becomes a founder at all, not whose company survives."
    )
    st.markdown(
        "**Matz & Freiberg (Columbia, 2023)** infer founder personality from tweets among "
        "already-known founders. We predict who *becomes* a founder — the target population "
        "is pre-emergence, not the already-emerged."
    )
    st.markdown(
        "**Arroyo et al. (2024)** reach 82% accuracy on flat-feature startup prediction. We "
        "test whether a knowledge-graph representation adds *incremental* predictive value "
        "over the flat-feature baseline."
    )


def page_methodology() -> None:
    st.subheader("Four-phase methodology")
    phases = [
        ("Phase 1", "Retrospective positive cases", "5–20 emerged founders"),
        ("Phase 1.5", "Matched-pair negative retrospective cases", "Project-level, anonymous"),
        ("Phase 2", "Self-case (author runs the tool on himself)", "Live in /Self-case"),
        ("Phase 3", "Knowledge graph construction", "From cohort ingestion"),
        ("Phase 4", "Comparative empirical evaluation", "Baseline vs KG-augmented + May 31 LOCKED predictions"),
    ]
    cols = st.columns(len(phases))
    for col, (tag, name, note) in zip(cols, phases, strict=False):
        with col:
            st.markdown(
                f"<div class='diff-card'><strong style='color:{EDHEC_BLUE}'>{tag}</strong><br>"
                f"<strong>{name}</strong><br>"
                f"<span style='color:#444; font-size:0.85rem'>{note}</span></div>",
                unsafe_allow_html=True,
            )

    st.subheader("Operational outcome definition")
    st.markdown(
        "<div class='claim-quote'>"
        "An individual is classified as having emerged if, within 24 months of their first "
        "measurable social-signal observation, they have publicly demonstrated at least ONE of: "
        "(a) primary income from a self-built creator/micro-entrepreneurship venture, "
        "(b) a verifiable revenue threshold of ≥$5k MRR or ≥$60k ARR, "
        "(c) a follower/subscriber threshold of ≥10k on the primary platform sustained ≥6 months, "
        "(d) external recognition — funding, acquisition, or top-100 rank in a niche-relevant index."
        "</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Verbatim from COMPREHENSIVE_PLAN §4.1. Researcher choice; documented honestly in the "
        "limitations chapter."
    )

    st.subheader("Data sources")
    sources = pd.DataFrame(
        [
            ["X (Twitter)", "Pre-launch posts via Wayback snapshots; snscrape blocked", "✅", "20 founders"],
            ["YouTube", "Long-form videos, transcripts, channel growth", "🔲", "Planned"],
            ["Reddit", "Subreddit comments, build-in-public posts", "🔲", "Planned"],
            ["Hacker News", "Show HN, comments, karma trajectory", "🔲", "Planned"],
            ["Product Hunt", "Launches, upvotes, maker history", "🔲", "Planned"],
            ["Substack", "Newsletter posts, subscriber milestones", "🔲", "Planned"],
            ["GitHub trending", "Repo activity, contributor patterns", "🔲", "Planned"],
            ["Google Trends", "Topic momentum, niche emergence signals", "🔲", "Planned"],
        ],
        columns=["Source", "What it captures", "Status", "Coverage"],
    )
    st.dataframe(sources, hide_index=True, use_container_width=True)
    st.caption("✅ shipped · 🟡 in progress · 🔲 planned")

    st.subheader("The May 31 commitment")
    st.markdown(
        "On **May 31, 2026** the framework is applied forward to approximately 30 currently-"
        "emerging founders. The predictions are cryptographically timestamped via a public git "
        "commit. Outcomes are re-evaluated at 12 months (May 2027) and 24 months (May 2028). "
        "This converts a retrospective study into a longitudinal one and directly addresses "
        "the survivorship-bias critique."
    )


def page_cohort() -> None:
    cohort = load_cohort()
    rows = cohort["rows"]
    df = pd.DataFrame(rows)

    total = len(df)
    emerged = int((df["emergence_status"] == "emerged").sum())
    non_emerged = int((df["emergence_status"] == "pending_verification").sum())
    avg_ingestion = float(df["data_ingestion_pct"].mean())

    st.subheader("Cohort status")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total cohort size", total)
    c2.metric("Emerged (positive class)", emerged)
    c3.metric("Negative class", non_emerged, help="Project-level anonymous negatives")
    c4.metric("Avg data ingestion", f"{avg_ingestion:.0f}%")

    display_cols = [
        "founder",
        "handle",
        "primary_platform",
        "emergence_status",
        "emergence_date_approx",
        "data_ingestion_pct",
        "notes",
    ]
    st.dataframe(df[display_cols], hide_index=True, use_container_width=True)

    st.info(
        "Cohort verification in progress. Final list locks Thu May 15. Outcome labels and "
        "full ingestion status published on this page weekly."
    )
    st.caption(
        f"Source: {cohort['_meta']['source']} · last updated {cohort['_meta']['last_updated']}"
    )


def page_roadmap() -> None:
    roadmap = load_roadmap()
    phases = roadmap["phases"]
    df = pd.DataFrame(phases)
    df["start_date"] = pd.to_datetime(df["start_date"])
    df["end_date"] = pd.to_datetime(df["end_date"])

    status_color = {"done": "#2ea44f", "in_progress": EDHEC_BLUE, "upcoming": "#959da5"}

    st.subheader("Roadmap to defence")
    fig = px.timeline(
        df,
        x_start="start_date",
        x_end="end_date",
        y="phase_name",
        color="status",
        color_discrete_map=status_color,
        hover_data=["date_range", "deliverable"],
    )
    fig.update_yaxes(autorange="reversed", title=None)
    fig.update_xaxes(title=None)
    fig.update_layout(height=520, margin=dict(l=10, r=10, t=10, b=10), legend_title_text="")
    st.plotly_chart(fig, use_container_width=True)

    in_progress = df[df["status"] == "in_progress"]
    if len(in_progress):
        next_milestone = in_progress.iloc[0]["phase_name"]
    else:
        upcoming = df[df["status"] == "upcoming"]
        next_milestone = upcoming.iloc[0]["phase_name"] if len(upcoming) else "—"

    c1, c2, c3 = st.columns(3)
    c1.metric("Next milestone", next_milestone)
    c2.metric("Submission deadline", "Jun 30, 2026")
    c3.metric("Defence date", "Jul 18, 2026")

    st.caption(
        f"Source: {roadmap['_meta']['source']} · "
        f"prediction lock {roadmap['_meta']['prediction_lock_date']}"
    )


def page_results() -> None:
    st.subheader("Model results & allocation")
    st.caption(
        "Surfaces outputs of `pipeline.py eval allocate`. Empty placeholders "
        "appear until the LLM scoring pass + negative-peer labels land."
    )

    eval_path = PROCESSED_DIR / "eval_metrics.csv"
    alloc_path = PROCESSED_DIR / "allocation.csv"

    if eval_path.exists():
        st.markdown("**Baseline vs KG-augmented**")
        df = pd.read_csv(eval_path)
        st.dataframe(df, use_container_width=True, hide_index=True)
        if {"name", "roc_auc"} <= set(df.columns):
            baseline_row = df[df["name"] == "baseline"]
            kg_row = df[df["name"] == "kg_augmented"]
            if len(baseline_row) and len(kg_row):
                delta_auc = (
                    kg_row.iloc[0]["roc_auc"] - baseline_row.iloc[0]["roc_auc"]
                )
                c1, c2, c3 = st.columns(3)
                c1.metric("Baseline ROC AUC", f"{baseline_row.iloc[0]['roc_auc']:.3f}")
                c2.metric("KG-augmented ROC AUC", f"{kg_row.iloc[0]['roc_auc']:.3f}")
                c3.metric("Δ AUC (KG vs baseline)", f"{delta_auc:+.3f}")
    else:
        st.info(
            "No evaluation metrics yet. Run `python pipeline.py eval` once "
            "scored signals and negative-cohort labels are in place."
        )

    if alloc_path.exists():
        st.markdown("**Capital allocation (fractional Kelly)**")
        df = pd.read_csv(alloc_path)
        show_cols = [c for c in [
            "person_id", "p_emerge", "allocation_normalised", "dollars_allocated"
        ] if c in df.columns]
        st.dataframe(df[show_cols].head(20), use_container_width=True, hide_index=True)
        st.caption(
            "Defaults: 1/4-Kelly @ 30x payoff, 10% per-person cap, $1M capital. "
            "Tunable via `AllocationParams` in `analysis/allocation.py`."
        )
    else:
        st.info(
            "No allocation table yet. Run `python pipeline.py allocate` after eval."
        )


def page_self_case() -> None:
    from analysis.self_case import self_case_view

    st.subheader("Self-case: predicting the author")
    st.caption(
        "Per DECISION_LOG iter-11: the self-case is Kris using the framework "
        "on his own X handle. Same ingestion, same scoring, same KG, same "
        "model. Demonstrates the framework's generalisability by example."
    )

    view = self_case_view()
    st.markdown(f"**Anchor handle:** `@{view.handle}` (`SELF_HANDLE` in `analysis/self_case.py`)")

    if not view.has_features:
        st.warning(
            f"No feature row yet. Status: {view.note}\n\n"
            f"To populate: ingest @{view.handle} via the platform collectors, "
            "run `python pipeline.py score person graph kg-features`."
        )
        return

    c1, c2, c3 = st.columns(3)
    if view.p_emerge is not None:
        c1.metric("P(emerge) prediction", f"{view.p_emerge:.3f}")
    else:
        c1.metric("P(emerge) prediction", "pending model")
    if view.cohort_percentile is not None:
        c2.metric("Cohort percentile", f"{view.cohort_percentile * 100:.0f}%")
    if view.feature_row:
        c3.metric("# signals ingested", int(view.feature_row.get("n_signals", 0)))

    if view.feature_row:
        st.markdown("**Per-person flat features**")
        feat_df = pd.DataFrame(
            [
                {"feature": k, "value": v}
                for k, v in view.feature_row.items()
                if k != "person_id" and v is not None
            ]
        )
        st.dataframe(feat_df, use_container_width=True, hide_index=True)

    if view.kg_row:
        st.markdown("**Knowledge-graph features**")
        kg_df = pd.DataFrame(
            [
                {"feature": k, "value": v}
                for k, v in view.kg_row.items()
                if k != "person_id" and v is not None
            ]
        )
        st.dataframe(kg_df, use_container_width=True, hide_index=True)

    st.info(view.note if view.note != "ok" else (
        "All artefacts present. P(emerge) is the KG-augmented model's prediction "
        "for the author. Cohort percentile compares it against the other persons "
        "in the labels file."
    ))


def page_backtest() -> None:
    st.subheader("Phase 4 retrospective backtest")
    st.caption(
        "Two-tier framework applied retrospectively at multiple dates, "
        "compared against random / signal-volume / recency baselines. "
        "Lift numbers become meaningful once negative-peer labels populate."
    )
    bt_path = PROCESSED_DIR / "backtest_results.csv"
    if not bt_path.exists():
        st.info(
            "No backtest results yet. Run `python pipeline.py backtest` "
            "after seed-labels + scoring."
        )
        return

    df = pd.read_csv(bt_path)
    st.markdown("**precision@k by strategy and backtest date**")
    pivot = df.pivot_table(
        index=["backtest_date", "strategy"],
        columns="k",
        values="precision_at_k",
        aggfunc="first",
    ).reset_index()
    st.dataframe(pivot, use_container_width=True, hide_index=True)

    st.markdown("**Lift vs base rate (precision@k / base_rate)**")
    if "lift_at_k" in df.columns:
        lift_pivot = df.pivot_table(
            index=["backtest_date", "strategy"],
            columns="k",
            values="lift_at_k",
            aggfunc="first",
        ).reset_index()
        st.dataframe(lift_pivot, use_container_width=True, hide_index=True)


def page_simulation() -> None:
    st.subheader("Monte Carlo simulation")
    st.caption(
        "Framework demonstration. Simulations show what the index would do "
        "under stated priors — they are NOT statistical claims that "
        "generalise beyond the cohort."
    )

    sim_tab, portfolio_tab, topic_tab = st.tabs(
        ["Founder emergence", "Portfolio", "Topic trajectory"]
    )

    with sim_tab:
        st.markdown("**Founder emergence — per-founder P(emerge) distribution**")
        c1, c2, c3 = st.columns(3)
        s1 = c1.slider("S1 mean (content cadence)", 0.0, 1.0, 0.5, 0.05, key="sim_s1")
        s3 = c2.slider("S3 mean (intent)", 0.0, 1.0, 0.4, 0.05, key="sim_s3")
        s4 = c3.slider("S4 mean (network)", 0.0, 1.0, 0.3, 0.05, key="sim_s4")
        n_iter = st.select_slider("n_iter", [200, 500, 1000, 2000, 5000], 1000)
        if st.button("Simulate emergence"):
            import warnings as _w

            from models.monte_carlo import simulate_founder_emergence
            with _w.catch_warnings():
                _w.simplefilter("ignore")
                _, summary = simulate_founder_emergence(
                    {"s1_mean": s1, "s3_mean": s3, "s4_mean": s4},
                    n_iter=n_iter, random_seed=42,
                )
            st.json(summary)

    with portfolio_tab:
        st.markdown("**Portfolio — fund-level emergence rate**")
        n_founders = st.number_input("# founders", 2, 20, 5, key="port_n")
        probs_text = st.text_input(
            "P(emerge) per founder, comma-separated",
            ",".join(["0.5"] * int(n_founders)),
            key="port_probs",
        )
        weights_text = st.text_input(
            "Weights, comma-separated (must sum to 1)",
            ",".join([f"{1/int(n_founders):.3f}"] * int(n_founders)),
            key="port_weights",
        )
        n_iter = st.select_slider(
            "n_iter (portfolio)", [200, 500, 1000, 5000], 1000, key="port_iter"
        )
        if st.button("Simulate portfolio", key="port_btn"):
            import numpy as _np

            from models.monte_carlo import simulate_portfolio
            try:
                probs = _np.array([float(x) for x in probs_text.split(",")])
                weights = _np.array([float(x) for x in weights_text.split(",")])
                _, summary = simulate_portfolio(
                    probs, weights, n_iter=n_iter, random_seed=42,
                )
                st.json(summary)
            except Exception as exc:
                st.error(f"Invalid input: {exc}")

    with topic_tab:
        st.markdown("**Topic trajectory — mainstream / niche / faded probabilities**")
        c1, c2 = st.columns(2)
        ev = c1.slider("Initial engagement velocity", 0.0, 100.0, 40.0, 1.0)
        align = c2.slider("Cross-creator alignment", 0.0, 1.0, 0.3, 0.05)
        horizon = st.slider("Horizon months", 3, 36, 18)
        n_iter = st.select_slider(
            "n_iter (topic)", [200, 500, 1000, 5000], 1000, key="topic_iter"
        )
        if st.button("Simulate trajectory", key="topic_btn"):
            import warnings as _w

            from models.monte_carlo import simulate_topic_trajectory
            with _w.catch_warnings():
                _w.simplefilter("ignore")
                _, summary = simulate_topic_trajectory(
                    {
                        "engagement_velocity": ev,
                        "cross_creator_alignment": align,
                        "lead_lag_position": 0.5,
                        "external_mention_growth": 1.0,
                        "months_since_first_signal": 6,
                    },
                    horizon_months=horizon, n_iter=n_iter, random_seed=42,
                )
            st.json(summary)


# ---------- entry ----------

def main() -> None:
    st.set_page_config(
        page_title="From Social Signals to Pre-Seed Allocation",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_css()
    header()

    st.sidebar.markdown("### Navigate")
    page = st.sidebar.radio(
        "Page",
        [
            "Thesis claim", "Methodology", "Cohort status", "Results",
            "Backtest", "Simulation", "Self-case", "Roadmap",
        ],
        label_visibility="collapsed",
    )
    st.sidebar.markdown("---")
    st.sidebar.caption(
        "Working artefact, not finished results. Defence: Jul 18, 2026."
    )

    if page == "Thesis claim":
        page_claim()
    elif page == "Methodology":
        page_methodology()
    elif page == "Cohort status":
        page_cohort()
    elif page == "Results":
        page_results()
    elif page == "Backtest":
        page_backtest()
    elif page == "Simulation":
        page_simulation()
    elif page == "Self-case":
        page_self_case()
    else:
        page_roadmap()

    footer()


if __name__ == "__main__":
    main()
