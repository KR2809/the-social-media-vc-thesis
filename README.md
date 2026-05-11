# the-social-media-vc-thesis

A data-driven pre-seed venture-capital allocation framework using only public
social-media signals. BBA thesis at EDHEC International BBA, 2025–26.

**Thesis title:** *From Social Signals to Entrepreneurial Emergence: A
Knowledge Graph Framework for Predicting Micro-Entrepreneurship in the
Creator Economy*
**Author:** Kristian Ratkov
**Supervisor:** George Tovstiga
**Submission:** June 30, 2026 · Defence: July 18, 2026

## What this repo contains

| Folder | Contents |
|---|---|
| `ingestion/` | Data collectors (X via snscrape + Wayback, YouTube, Reddit, HN, Product Hunt, GitHub, Google Trends) |
| `scoring/` | LLM-based signal scoring (Claude Haiku 4.5 default; Sonnet 4.6 for taxonomy) |
| `analysis/` | Topic momentum (Tier 1) + knowledge-graph construction (Tier 2) |
| `prompts/` | Versioned LLM prompts |
| `models/` | Baseline (flat-feature) + KG-augmented models + evaluation |
| `dashboard/` | Streamlit demo |
| `data/` | raw / interim / processed (gitignored — never committed) |
| `tests/` | Unit tests |
| `docs/` | Methodology notes, schema docs, prompt design notes |
| `STATUS_UPDATES.md` | Append-only journal of Claude Code work sessions |

## Setup

```bash
cp .env.example .env
# fill in API keys
uv sync   # or: pip install -e .[dev]
```

## Running the pipeline (once built)

```bash
# Phase 1: collect data
python -m ingestion.run_all --cohort cohort_verified.csv

# Phase 2: score signals
python -m scoring.run --model claude-haiku-4-5

# Phase 3: build knowledge graph
python -m analysis.build_graph

# Phase 4: train + evaluate
python -m models.train_compare

# Phase 5: launch dashboard
streamlit run dashboard/app.py
```

## License

MIT for code, CC-BY 4.0 for non-code artefacts (signal taxonomy, KG schema,
prompts). The repo becomes public on **May 31, 2026** when prospective
predictions are locked (per Move A of the thesis methodology — the
registered-prediction commitment).

## Repository status

This repo is under active development for the May 31, 2026 prediction-lock
deadline. See `STATUS_UPDATES.md` for the current session journal.
