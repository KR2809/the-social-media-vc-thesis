"""Monte Carlo simulation module (Phase 3 framework extension #3).

Implements the four simulation functions specified in
`00_PLANNING/cc_prompts_phase3_monte_carlo.md`. They turn the
predictive index from "ranked list" into "probabilistic forecast with
uncertainty bands."

Epistemic status (load-bearing — also restated per-function):

    This is framework demonstration. The simulations show what the
    index would do under the stated priors. They are NOT statistical
    claims that generalise beyond the cohort. Priors are calibrated
    from n~=25 cohort summary statistics.

Calibration sources are read from JSON files in
`data/processed/models/` when present (`feature_weights.json`,
`calibration.json`, `topic_dynamics.json`). If absent, the simulations
use documented weak priors and emit a single-line warning — they
remain usable for illustrative demos even without full upstream
calibration.

Pure numpy + scipy.stats — no new deps. Every public function takes a
`random_seed` for reproducibility and returns both the full traces
and a structured summary dict.
"""

from __future__ import annotations

import json
import logging
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import beta as beta_dist
from scipy.stats import multivariate_normal, norm

logger = logging.getLogger(__name__)

_MODELS_DIR = Path("data/processed/models")
_EPISTEMIC = (
    "This is framework demonstration. The simulation shows what the "
    "index would do under the stated priors. It is NOT a statistical "
    "claim that generalises beyond the cohort. Priors are calibrated "
    "from n~=25 cohort summary statistics."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _summary(traces: np.ndarray, ci_pct: float = 0.95) -> dict[str, float]:
    """Standard summary dict for continuous-valued traces."""
    if len(traces) == 0:
        return {
            "mean": 0.0, "median": 0.0, "lower_ci": 0.0, "upper_ci": 0.0,
            "std": 0.0, "mode_approx": 0.0, "n": 0,
        }
    lo = (1 - ci_pct) / 2 * 100
    hi = (1 + ci_pct) / 2 * 100
    # Approximate mode via 50-bin histogram centre.
    hist, edges = np.histogram(traces, bins=min(50, max(5, len(traces) // 20)))
    mode_idx = int(np.argmax(hist))
    mode_approx = float(0.5 * (edges[mode_idx] + edges[mode_idx + 1]))
    return {
        "mean": float(np.mean(traces)),
        "median": float(np.median(traces)),
        "lower_ci": float(np.percentile(traces, lo)),
        "upper_ci": float(np.percentile(traces, hi)),
        "std": float(np.std(traces, ddof=1)) if len(traces) > 1 else 0.0,
        "mode_approx": mode_approx,
        "n": int(len(traces)),
    }


def _load_json_optional(path: Path, fallback_warning: str) -> dict | None:
    if not path.exists():
        warnings.warn(fallback_warning, stacklevel=3)
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        warnings.warn(
            f"could not parse {path}: {exc}; falling back to weak priors", stacklevel=3
        )
        return None


# ---------------------------------------------------------------------------
# Function 1 — bootstrap_metric_ci
# ---------------------------------------------------------------------------


def bootstrap_metric_ci(
    predictions: np.ndarray,
    outcomes: np.ndarray,
    metric_fn: Callable[[np.ndarray, np.ndarray], float],
    n_iter: int = 10_000,
    ci_pct: float = 0.95,
    random_seed: int = 42,
) -> tuple[np.ndarray, dict[str, float]]:
    """Bootstrap confidence intervals for any sklearn-style metric.

    Mathematical description.
        For n_iter iterations, resample (predictions, outcomes) with
        replacement (same n), compute metric_fn on the bootstrap
        sample, and collect. Returns the trace plus mean / median /
        lower-CI / upper-CI / std / approximate mode.

    Calibration source.
        None — this is purely a resampling procedure on observed data.

    Epistemic status.
        This is framework demonstration. The simulation shows what the
        index would do under the stated priors. It is NOT a statistical
        claim that generalises beyond the cohort. Priors are calibrated
        from n~=25 cohort summary statistics.

    Caveats.
        - If a bootstrap sample is degenerate for the metric (e.g. all
          outcomes equal for ROC AUC), the iteration is skipped and
          documented in `summary["n_skipped"]`.
        - n must equal len(predictions) == len(outcomes).
        - The metric_fn must accept (y_true, y_score) in that order.

    Example.
        >>> from sklearn.metrics import roc_auc_score
        >>> import numpy as np
        >>> rng = np.random.default_rng(0)
        >>> p = rng.beta(2, 2, 30)
        >>> y = (rng.random(30) < p).astype(int)
        >>> traces, summary = bootstrap_metric_ci(p, y, roc_auc_score, n_iter=500)
        >>> 0.0 < summary["mean"] < 1.0
        True
    """
    if len(predictions) != len(outcomes):
        raise ValueError(
            f"length mismatch: predictions={len(predictions)} outcomes={len(outcomes)}"
        )
    n = len(predictions)
    rng = np.random.default_rng(random_seed)
    samples: list[float] = []
    n_skipped = 0
    for _ in range(n_iter):
        idx = rng.integers(0, n, size=n)
        y = outcomes[idx]
        p = predictions[idx]
        # Skip degenerate samples for metrics that need both classes.
        if len(np.unique(y)) < 2:
            n_skipped += 1
            continue
        try:
            samples.append(float(metric_fn(y, p)))
        except (ValueError, ZeroDivisionError):
            n_skipped += 1
            continue

    traces = np.asarray(samples, dtype=float)
    summary = _summary(traces, ci_pct=ci_pct)
    summary["n_skipped"] = n_skipped
    summary["ci_pct"] = ci_pct
    return traces, summary


# ---------------------------------------------------------------------------
# Function 2 — simulate_founder_emergence
# ---------------------------------------------------------------------------


def _sigmoid(x: float | np.ndarray) -> float | np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def simulate_founder_emergence(
    signal_vector: dict[str, float],
    cohort_priors: dict[str, dict[str, float]] | None = None,
    horizon_months: int = 24,
    n_iter: int = 10_000,
    random_seed: int = 42,
    weights_path: Path | None = None,
    calibration_path: Path | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Per-founder emergence outcome distribution at a fixed horizon.

    Mathematical description.
        For each iteration:
          1. Sample a "true" signal score for each taxonomy dimension
             present in `signal_vector` from a Beta prior parameterised
             by `cohort_priors[dim]` (alpha, beta). If `cohort_priors`
             is None / missing the dim, use Beta(2, 2) centred at the
             observed value.
          2. Combine into a single emergence score via the locked
             baseline-model linear combination (weights from
             `feature_weights.json`, else uniform).
          3. Sample emergence | score from a calibrated logistic:
                P(emergence) = sigmoid(beta_0 + beta_1 * score)
             where (beta_0, beta_1) come from `calibration.json`,
             else (beta_0=-2.0, beta_1=4.0) — moderate-strength prior.
          4. Sample Bernoulli(P(emergence)) for the horizon outcome.

    Calibration source.
        - feature_weights.json (defaults to uniform with warning)
        - calibration.json (defaults to weak prior with warning)
        - cohort_priors (passed in or defaults to Beta(2, 2))

    Epistemic status.
        This is framework demonstration. The simulation shows what the
        index would do under the stated priors. It is NOT a statistical
        claim that generalises beyond the cohort. Priors are calibrated
        from n~=25 cohort summary statistics.

    Caveats.
        - horizon_months is an input the model is NOT trained on; the
          horizon-dependence is approximated by passing through the
          calibration. Future work: time-varying hazards.
        - signal_vector keys that don't appear in feature_weights are
          ignored (no-op rather than error).

    Example.
        >>> sv = {"s1_mean": 0.6, "s3_mean": 0.4, "n_signals": 30.0}
        >>> traces, summary = simulate_founder_emergence(
        ...     sv, n_iter=500, random_seed=0
        ... )
        >>> 0.0 <= summary["P_emergence_mean"] <= 1.0
        True
    """
    rng = np.random.default_rng(random_seed)

    weights_path = weights_path or _MODELS_DIR / "feature_weights.json"
    calibration_path = calibration_path or _MODELS_DIR / "calibration.json"

    weights_json = _load_json_optional(
        weights_path,
        f"{weights_path} not found; using uniform weights for emergence simulation",
    )
    weights = weights_json if isinstance(weights_json, dict) else None

    calib = _load_json_optional(
        calibration_path,
        f"{calibration_path} not found; using weak (b0=-2.0, b1=4.0) logistic prior",
    )
    beta_0 = float((calib or {}).get("beta_0", -2.0))
    beta_1 = float((calib or {}).get("beta_1", 4.0))

    cohort_priors = cohort_priors or {}

    traces = np.zeros(n_iter, dtype=int)
    p_traces = np.zeros(n_iter, dtype=float)
    for i in range(n_iter):
        score = 0.0
        for dim, observed in signal_vector.items():
            prior = cohort_priors.get(dim)
            if prior and "alpha" in prior and "beta" in prior:
                sampled = float(beta_dist.rvs(prior["alpha"], prior["beta"], random_state=rng))
            else:
                # Centre Beta(2, 2)-shaped jitter around the observed value
                # (clipped to [0, 1] only for graded dims; counts pass through).
                if 0.0 <= observed <= 1.0:
                    a, b = 2.0, 2.0
                    jitter = float(beta_dist.rvs(a, b, random_state=rng)) - 0.5
                    sampled = float(np.clip(observed + 0.2 * jitter, 0.0, 1.0))
                else:
                    sampled = float(observed)
            w = float(weights.get(dim, 1.0)) if weights else 1.0
            score += w * sampled
        # Normalise the score so the logistic regime is meaningful.
        if weights:
            denom = sum(abs(float(v)) for v in weights.values()) or 1.0
        else:
            denom = float(max(1, len(signal_vector)))
        normalised = score / denom
        p_emerge = float(_sigmoid(beta_0 + beta_1 * normalised))
        p_traces[i] = p_emerge
        traces[i] = int(rng.random() < p_emerge)

    summary = {
        "P_emergence_mean": float(p_traces.mean()),
        "P_emergence_median": float(np.median(p_traces)),
        "P_emergence_lower_ci": float(np.percentile(p_traces, 2.5)),
        "P_emergence_upper_ci": float(np.percentile(p_traces, 97.5)),
        "outcome_rate": float(traces.mean()),
        "horizon_months": horizon_months,
        "n_iter": n_iter,
        "calibration_used": "json" if calib else "weak_prior",
        "weights_used": "json" if weights else "uniform",
    }
    return traces, summary


# ---------------------------------------------------------------------------
# Function 3 — simulate_topic_trajectory
# ---------------------------------------------------------------------------


def simulate_topic_trajectory(
    topic_state: dict[str, float],
    transition_dynamics: dict[str, dict[str, float]] | None = None,
    horizon_months: int = 18,
    mainstream_threshold: float = 80.0,
    fade_threshold: float = 10.0,
    n_iter: int = 10_000,
    random_seed: int = 42,
    dynamics_path: Path | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Roll a topic's state vector forward and classify the terminal outcome.

    Mathematical description.
        Each iteration:
          1. Initialise state[t=0] from `topic_state`.
          2. For t in 1..horizon_months, update each component with a
             Gaussian increment whose mean (drift) and std (vol) come
             from `transition_dynamics[component]`.
          3. At t = horizon, classify the trajectory:
                "mainstream"        if engagement_velocity >= mainstream_threshold
                "faded"             if engagement_velocity <= fade_threshold
                "niche_persistent"  otherwise
        Returns the categorical trace and a summary with the
        probability of each outcome.

    Calibration source.
        - transition_dynamics (passed in or read from topic_dynamics.json)
        - thresholds (passed in; defaults: 80 mainstream, 10 fade)

    Epistemic status.
        This is framework demonstration. The simulation shows what the
        index would do under the stated priors. It is NOT a statistical
        claim that generalises beyond the cohort. Priors are calibrated
        from n~=25 cohort summary statistics.

    Caveats.
        - The transition model is Gaussian-RW; it does not capture
          discrete shocks or jump diffusion.
        - Thresholds are on raw engagement_velocity scale; calibrate
          against your own series.

    Example.
        >>> state = {
        ...     "engagement_velocity": 40.0,
        ...     "cross_creator_alignment": 0.3,
        ...     "lead_lag_position": 0.5,
        ...     "external_mention_growth": 1.0,
        ...     "months_since_first_signal": 6,
        ... }
        >>> traces, summary = simulate_topic_trajectory(
        ...     state, n_iter=500, random_seed=0
        ... )
        >>> abs(summary["P_mainstream"] + summary["P_niche"] + summary["P_fade"] - 1) < 1e-6
        True
    """
    rng = np.random.default_rng(random_seed)
    dynamics_path = dynamics_path or _MODELS_DIR / "topic_dynamics.json"

    if transition_dynamics is None:
        loaded = _load_json_optional(
            dynamics_path,
            f"{dynamics_path} not found; using weak random-walk priors for topic dynamics",
        )
        transition_dynamics = loaded or {
            "engagement_velocity": {"drift": 0.0, "vol": 5.0},
            "cross_creator_alignment": {"drift": 0.0, "vol": 0.05},
            "lead_lag_position": {"drift": 0.0, "vol": 0.05},
            "external_mention_growth": {"drift": 0.0, "vol": 0.2},
        }

    components = [k for k in topic_state if k != "months_since_first_signal"]
    outcomes: list[str] = []
    final_velocities: list[float] = []

    for _ in range(n_iter):
        state = {k: float(v) for k, v in topic_state.items()}
        for _t in range(horizon_months):
            for c in components:
                d = transition_dynamics.get(c, {"drift": 0.0, "vol": 0.1})
                state[c] += float(rng.normal(d.get("drift", 0.0), d.get("vol", 0.1)))
        v = state.get("engagement_velocity", 0.0)
        final_velocities.append(v)
        if v >= mainstream_threshold:
            outcomes.append("mainstream")
        elif v <= fade_threshold:
            outcomes.append("faded")
        else:
            outcomes.append("niche_persistent")

    traces = np.asarray(outcomes, dtype=object)
    n = len(traces)
    p_main = float((traces == "mainstream").sum() / n) if n else 0.0
    p_fade = float((traces == "faded").sum() / n) if n else 0.0
    p_niche = float((traces == "niche_persistent").sum() / n) if n else 0.0

    summary = {
        "P_mainstream": p_main,
        "P_niche": p_niche,
        "P_fade": p_fade,
        "engagement_velocity_mean_final": float(np.mean(final_velocities)) if n else 0.0,
        "engagement_velocity_ci": (
            float(np.percentile(final_velocities, 2.5)) if n else 0.0,
            float(np.percentile(final_velocities, 97.5)) if n else 0.0,
        ),
        "horizon_months": horizon_months,
        "n_iter": n_iter,
        "dynamics_source": "json" if transition_dynamics else "weak_prior",
    }
    return traces, summary


# ---------------------------------------------------------------------------
# Function 4 — simulate_portfolio
# ---------------------------------------------------------------------------


def simulate_portfolio(
    founder_emergence_probs: np.ndarray,
    weights: np.ndarray,
    correlation_matrix: np.ndarray | None = None,
    n_iter: int = 10_000,
    random_seed: int = 42,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Simulate fund-level emergence rates under correlated outcomes.

    Mathematical description.
        For each iteration:
          1. If correlation_matrix is None or identity: sample
             independent Bernoulli outcomes y_i ~ Bernoulli(p_i).
             Otherwise sample correlated Bernoullis via a Gaussian
             copula: draw z ~ N(0, correlation_matrix), set
             y_i = 1 iff Phi(z_i) < p_i.
          2. Portfolio outcome = sum(weights_i * y_i). Weights must
             sum to 1.0.

    Calibration source.
        Inputs are passed in directly. No JSON dependency.

    Epistemic status.
        This is framework demonstration. The simulation shows what the
        index would do under the stated priors. It is NOT a statistical
        claim that generalises beyond the cohort. Priors are calibrated
        from n~=25 cohort summary statistics.

    Caveats.
        - The Gaussian copula imposes a specific dependence structure;
          real founder outcomes may have heavier-tailed dependence.
        - weights should be non-negative and sum to 1. Negative weights
          (shorts) are accepted but unusual for a pre-seed portfolio.

    Example.
        >>> import numpy as np
        >>> p = np.array([0.6, 0.4, 0.2])
        >>> w = np.array([0.5, 0.3, 0.2])
        >>> traces, summary = simulate_portfolio(p, w, n_iter=500, random_seed=0)
        >>> 0.0 <= summary["mean"] <= 1.0
        True
    """
    probs = np.asarray(founder_emergence_probs, dtype=float)
    w = np.asarray(weights, dtype=float)
    if len(probs) != len(w):
        raise ValueError(f"length mismatch: probs={len(probs)} weights={len(w)}")
    k = len(probs)
    rng = np.random.default_rng(random_seed)

    if correlation_matrix is not None:
        cov_check = np.asarray(correlation_matrix, dtype=float)
        if cov_check.shape != (k, k):
            raise ValueError(
                f"correlation_matrix must be {k}x{k}, got {cov_check.shape}"
            )

    if correlation_matrix is None or np.allclose(correlation_matrix, np.eye(k)):
        u = rng.random((n_iter, k))
        outcomes = (u < probs).astype(int)
    else:
        cov = np.asarray(correlation_matrix, dtype=float)
        # Gaussian copula: z ~ N(0, cov); u = Phi(z); y = u < p
        mvn = multivariate_normal(mean=np.zeros(k), cov=cov, allow_singular=True)
        z = mvn.rvs(size=n_iter, random_state=rng)
        if z.ndim == 1:
            z = z.reshape(-1, k)
        u = norm.cdf(z)
        outcomes = (u < probs).astype(int)

    traces = outcomes @ w
    base = _summary(traces)
    base.update(
        {
            "max_single_contribution": float(np.max(w * probs)),
            "concentration_hhi": float(np.sum(w**2)),
            "n_winners_mean": float(outcomes.sum(axis=1).mean()),
            "n_winners_lower_ci": float(np.percentile(outcomes.sum(axis=1), 2.5)),
            "n_winners_upper_ci": float(np.percentile(outcomes.sum(axis=1), 97.5)),
            "n_iter": n_iter,
        }
    )
    return traces, base
