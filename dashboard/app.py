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
        f"<h1 style='margin-bottom:0.1rem'>From Social Signals to Entrepreneurial Emergence</h1>",
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
        "Observable, multi-platform, public behavioural signals — structured as a knowledge "
        "graph — can predict which individuals will emerge as successful micro-entrepreneurs "
        "in the creator economy <em>before</em> they formally launch."
        "</div>",
        unsafe_allow_html=True,
    )
    st.caption("Paraphrased from the locked thesis title and COMPREHENSIVE_PLAN §1.")

    st.subheader("The research question")
    st.markdown(
        "<div class='claim-quote'>"
        "Can social media behavioural signals predict which individuals will emerge as "
        "successful micro-entrepreneurs in the creator economy?"
        "</div>",
        unsafe_allow_html=True,
    )
    st.caption("Verbatim from COMPREHENSIVE_PLAN §2.1.")

    st.subheader("Five differentiators")
    diffs = [
        ("Individual-level", "Not company-level. The unit of analysis is the person before the venture."),
        ("Pre-launch", "Not post-founding. Signals are read in the window before a formal venture exists."),
        ("Creator economy", "A specific, growing niche — not generic startups, not VC-backed teams."),
        ("Multi-signal integration", "Multiple platforms, not just X. YouTube, Reddit, HN, PH, GH, Substack, GTrends."),
        ("Knowledge-graph methodology", "Relational structure, not flat features. Topics, people, projects, time."),
    ]
    cols = st.columns(5)
    for col, (title, body) in zip(cols, diffs):
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
        ("Phase 2", "Reflexive self-case", "Under review"),
        ("Phase 3", "Knowledge graph construction", "From cohort ingestion"),
        ("Phase 4", "Comparative empirical evaluation", "Baseline vs KG-augmented + May 31 LOCKED predictions"),
    ]
    cols = st.columns(len(phases))
    for col, (tag, name, note) in zip(cols, phases):
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


# ---------- entry ----------

def main() -> None:
    st.set_page_config(
        page_title="From Social Signals to Entrepreneurial Emergence",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_css()
    header()

    st.sidebar.markdown(f"### Navigate")
    page = st.sidebar.radio(
        "Page",
        ["Thesis claim", "Methodology", "Cohort status", "Roadmap"],
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
    else:
        page_roadmap()

    footer()


if __name__ == "__main__":
    main()
