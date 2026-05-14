-- Initial schema for thesis-social-signal-fund Supabase project.
-- DECISION_LOG iter-13 (2026-05-14): Option C hybrid storage.
-- This is the canonical mirror of data/processed/*.parquet + data/processed/*.csv
-- and the source the production FastAPI layer reads from (`--source supabase`).
--
-- Design notes:
-- - All tables include a `mirror_synced_at` column with a default of now() for
--   independent ingestion-timestamp provenance (per iter-13 §3 rationale).
-- - Primary keys match the parquet's natural keys exactly so the sync script
--   is a clean upsert.
-- - For tables that don't have an obvious natural key (eval_metrics with one
--   row per (model_name, run_date), backtest_results with one row per
--   (backtest_date, strategy, k)), composite primary keys are declared.
-- - All graded-signal columns are nullable doubles to match the parquet's
--   "score absent" semantics.
-- - Engagement on signal_events is stored as JSONB (the parquet stores it as a
--   PyArrow struct, but JSONB round-trips losslessly and is far easier to query).
-- - metadata on signal_events is stored as JSONB.
-- - Read-only access for the thesis appendix is granted via the Supabase
--   `anon` role; write access via `service_role` (sync script only).

-- ---------------------------------------------------------------------------
-- 1. signal_events — unified, per-platform raw SignalEvents
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS signal_events (
    signal_id        TEXT PRIMARY KEY,
    person_id        TEXT NOT NULL,
    timestamp        TIMESTAMPTZ NOT NULL,
    platform         TEXT NOT NULL,
    raw_text         TEXT,
    engagement       JSONB,
    metadata         JSONB,
    collected_at     TIMESTAMPTZ NOT NULL,
    source           TEXT,
    mirror_synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_signal_events_person      ON signal_events(person_id);
CREATE INDEX IF NOT EXISTS idx_signal_events_platform    ON signal_events(platform);
CREATE INDEX IF NOT EXISTS idx_signal_events_timestamp   ON signal_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_signal_events_pp_ts       ON signal_events(person_id, timestamp);

-- ---------------------------------------------------------------------------
-- 2. scored_signals — LLM-scored output of scoring/score_signals.py
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scored_signals (
    signal_id                    TEXT PRIMARY KEY,
    person_id                    TEXT NOT NULL,
    platform                     TEXT NOT NULL,
    timestamp                    TIMESTAMPTZ NOT NULL,
    prompt_version               TEXT NOT NULL,
    model                        TEXT NOT NULL,
    -- S1: content creation pattern
    s1_output_cadence            DOUBLE PRECISION,
    s1_format_diversity          DOUBLE PRECISION,
    s1_build_in_public           DOUBLE PRECISION,
    s1_domain_coherence          DOUBLE PRECISION,
    s1_original_synthesis        DOUBLE PRECISION,
    s1_production_quality        DOUBLE PRECISION,
    -- S2: consumption signal
    s2_reading_list_breadth      DOUBLE PRECISION,
    s2_specialist_vs_generalist  DOUBLE PRECISION,
    s2_highbrow_mix              DOUBLE PRECISION,
    s2_cross_domain              DOUBLE PRECISION,
    s2_tool_fascination          DOUBLE PRECISION,
    -- S3: expressed intention
    s3_explicit_goal             DOUBLE PRECISION,
    s3_frustration_to_idea       DOUBLE PRECISION,
    s3_public_commitment         DOUBLE PRECISION,
    s3_recurring_theme           DOUBLE PRECISION,
    s3_recruitment               DOUBLE PRECISION,
    s3_counterfactual_future_self DOUBLE PRECISION,
    -- S4: network behaviour
    s4_operator_proximity        DOUBLE PRECISION,
    s4_mentor_engagement         DOUBLE PRECISION,
    s4_reciprocity               DOUBLE PRECISION,
    s4_community_embedding       DOUBLE PRECISION,
    s4_sustained_relationship    DOUBLE PRECISION,
    -- S5: track record (framework extension; mostly null for non-Substack cohort)
    s5_verifiable_claim          DOUBLE PRECISION,
    s5_claim_specificity         DOUBLE PRECISION,
    s5_lead_time_months          DOUBLE PRECISION,
    -- S6: topic momentum (framework extension)
    s6_topic_label               TEXT,
    s6_topic_specificity         DOUBLE PRECISION,
    -- Holistic + flags + provenance
    overall_signal_strength      DOUBLE PRECISION,
    flags                        TEXT,
    scored_at                    TIMESTAMPTZ NOT NULL,
    raw_response                 TEXT,
    mirror_synced_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_scored_signals_person     ON scored_signals(person_id);
CREATE INDEX IF NOT EXISTS idx_scored_signals_topic      ON scored_signals(s6_topic_label);
CREATE INDEX IF NOT EXISTS idx_scored_signals_timestamp  ON scored_signals(timestamp);

-- ---------------------------------------------------------------------------
-- 3. person_features — per-person flat rollup (analysis/person_features.py)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS person_features (
    person_id              TEXT PRIMARY KEY,
    n_signals              BIGINT,
    n_platforms            BIGINT,
    first_signal_date      TIMESTAMPTZ,
    last_signal_date       TIMESTAMPTZ,
    active_days            DOUBLE PRECISION,
    mean_signal_strength   DOUBLE PRECISION,
    max_signal_strength    DOUBLE PRECISION,
    s1_mean                DOUBLE PRECISION,
    s2_mean                DOUBLE PRECISION,
    s3_mean                DOUBLE PRECISION,
    s4_mean                DOUBLE PRECISION,
    bip_signals            DOUBLE PRECISION,
    explicit_goal_signals  DOUBLE PRECISION,
    recruitment_signals    DOUBLE PRECISION,
    mirror_synced_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 4. kg_features — per-person KG-derived features (analysis/kg_features.py)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kg_features (
    person_id            TEXT PRIMARY KEY,
    degree_centrality    DOUBLE PRECISION,
    clustering_coeff     DOUBLE PRECISION,
    topic_diversity      DOUBLE PRECISION,
    n_topics             BIGINT,
    n_signals            BIGINT,
    n_platforms          BIGINT,
    bip_triad            BIGINT,
    mean_signal_strength DOUBLE PRECISION,
    mirror_synced_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 5. outcome_labels — training labels for the predictive models
-- emerged ∈ {0, 1, -1}; -1 is the self-case sentinel (excluded from training).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS outcome_labels (
    person_id        TEXT PRIMARY KEY,
    emerged          SMALLINT NOT NULL CHECK (emerged IN (-1, 0, 1)),
    source           TEXT,
    mirror_synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 6. negative_peers_registry — anonymous project-level negatives (iter-6)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS negative_peers_registry (
    peer_id                       TEXT PRIMARY KEY,
    matched_positive_niche        TEXT,
    matched_emergence_quarter     TEXT,
    public_signals_available      BOOLEAN,
    outcome_class                 TEXT,
    notes                         TEXT,
    registered_at                 TEXT,
    mirror_synced_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 7. eval_metrics — baseline vs KG-augmented evaluation results
-- One row per model (baseline | kg_augmented). Re-runs UPSERT.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eval_metrics (
    name             TEXT PRIMARY KEY,
    roc_auc          DOUBLE PRECISION,
    pr_auc           DOUBLE PRECISION,
    f1_at_0_5        DOUBLE PRECISION,
    precision_at_3   DOUBLE PRECISION,
    precision_at_5   DOUBLE PRECISION,
    lift_at_5        DOUBLE PRECISION,
    brier            DOUBLE PRECISION,
    n                BIGINT,
    n_pos            BIGINT,
    roc_auc_ci_lo    DOUBLE PRECISION,
    roc_auc_ci_hi    DOUBLE PRECISION,
    pr_auc_ci_lo     DOUBLE PRECISION,
    pr_auc_ci_hi     DOUBLE PRECISION,
    mirror_synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 8. backtest_results — Phase 4 retrospective backtest output
-- Composite key: one row per (backtest_date, strategy, k).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS backtest_results (
    backtest_date    DATE NOT NULL,
    strategy         TEXT NOT NULL,
    k                INTEGER NOT NULL,
    n_hits           INTEGER,
    base_rate        DOUBLE PRECISION,
    precision_at_k   DOUBLE PRECISION,
    lift_at_k        DOUBLE PRECISION,
    mirror_synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (backtest_date, strategy, k)
);

-- ---------------------------------------------------------------------------
-- 9. allocation — fractional-Kelly capital allocation per person
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS allocation (
    person_id              TEXT PRIMARY KEY,
    p_emerge               DOUBLE PRECISION,
    kelly_raw              DOUBLE PRECISION,
    kelly_fractional       DOUBLE PRECISION,
    allocation_capped      DOUBLE PRECISION,
    allocation_normalised  DOUBLE PRECISION,
    dollars_allocated      DOUBLE PRECISION,
    mirror_synced_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 10. topic_momentum_metrics — Tier-1 per-keyword momentum
-- Composite key on (keyword, geo).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS topic_momentum_metrics (
    keyword          TEXT NOT NULL,
    geo              TEXT NOT NULL DEFAULT '',
    slope_4w         DOUBLE PRECISION,
    slope_12w        DOUBLE PRECISION,
    delta_4w         DOUBLE PRECISION,
    delta_12w        DOUBLE PRECISION,
    latest           DOUBLE PRECISION,
    peak             DOUBLE PRECISION,
    n_weeks          INTEGER,
    acceleration     DOUBLE PRECISION,
    mirror_synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (keyword, geo)
);

-- ---------------------------------------------------------------------------
-- 11. discovered_topics — auto-topic-discovery output (iter-11)
-- Composite key on (topic, source) since the same string can appear in both
-- "cohort" and "trends_rising" sources (though we dedup in the script).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS discovered_topics (
    topic            TEXT NOT NULL,
    source           TEXT NOT NULL,
    n_signals        DOUBLE PRECISION,
    mean_strength    DOUBLE PRECISION,
    cohort_score     DOUBLE PRECISION,
    rising_score     DOUBLE PRECISION,
    rank             INTEGER,
    mirror_synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (topic, source)
);

-- ---------------------------------------------------------------------------
-- 12. locked_predictions — the sacred May-31 prospective predictions
-- The whole record is stored as JSONB so the schema can evolve without
-- breaking the lock. Primary key = lock_date.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS locked_predictions (
    lock_date         DATE PRIMARY KEY,
    framework_version TEXT NOT NULL,
    git_commit        TEXT,
    n_predictions     INTEGER,
    record            JSONB NOT NULL,
    sha256            TEXT NOT NULL,
    locked_at         TIMESTAMPTZ NOT NULL,
    mirror_synced_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 13. snapshots — manifest of GitHub-released data snapshots
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_version TEXT PRIMARY KEY,
    git_commit       TEXT NOT NULL,
    github_release_url TEXT,
    file_count       INTEGER,
    total_bytes      BIGINT,
    sha256_manifest  TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Row-Level Security: anon read-only, service_role full access
-- ---------------------------------------------------------------------------
ALTER TABLE signal_events           ENABLE ROW LEVEL SECURITY;
ALTER TABLE scored_signals          ENABLE ROW LEVEL SECURITY;
ALTER TABLE person_features         ENABLE ROW LEVEL SECURITY;
ALTER TABLE kg_features             ENABLE ROW LEVEL SECURITY;
ALTER TABLE outcome_labels          ENABLE ROW LEVEL SECURITY;
ALTER TABLE negative_peers_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE eval_metrics            ENABLE ROW LEVEL SECURITY;
ALTER TABLE backtest_results        ENABLE ROW LEVEL SECURITY;
ALTER TABLE allocation              ENABLE ROW LEVEL SECURITY;
ALTER TABLE topic_momentum_metrics  ENABLE ROW LEVEL SECURITY;
ALTER TABLE discovered_topics       ENABLE ROW LEVEL SECURITY;
ALTER TABLE locked_predictions      ENABLE ROW LEVEL SECURITY;
ALTER TABLE snapshots               ENABLE ROW LEVEL SECURITY;

-- Public read for the thesis-appendix examiners — every table is queryable
-- by anyone with the anon key (publicly visible in the appendix).
CREATE POLICY "anon read signal_events"           ON signal_events           FOR SELECT TO anon USING (true);
CREATE POLICY "anon read scored_signals"          ON scored_signals          FOR SELECT TO anon USING (true);
CREATE POLICY "anon read person_features"         ON person_features         FOR SELECT TO anon USING (true);
CREATE POLICY "anon read kg_features"             ON kg_features             FOR SELECT TO anon USING (true);
CREATE POLICY "anon read outcome_labels"          ON outcome_labels          FOR SELECT TO anon USING (true);
CREATE POLICY "anon read negative_peers_registry" ON negative_peers_registry FOR SELECT TO anon USING (true);
CREATE POLICY "anon read eval_metrics"            ON eval_metrics            FOR SELECT TO anon USING (true);
CREATE POLICY "anon read backtest_results"        ON backtest_results        FOR SELECT TO anon USING (true);
CREATE POLICY "anon read allocation"              ON allocation              FOR SELECT TO anon USING (true);
CREATE POLICY "anon read topic_momentum_metrics"  ON topic_momentum_metrics  FOR SELECT TO anon USING (true);
CREATE POLICY "anon read discovered_topics"       ON discovered_topics       FOR SELECT TO anon USING (true);
CREATE POLICY "anon read locked_predictions"      ON locked_predictions      FOR SELECT TO anon USING (true);
CREATE POLICY "anon read snapshots"               ON snapshots               FOR SELECT TO anon USING (true);

-- (service_role bypasses RLS automatically — no policy needed.)
