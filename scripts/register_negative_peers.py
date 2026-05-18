"""Negative-peer picking canvas.

Kris fills this file in row-by-row over a 48-hour window. Each section
below corresponds to one niche/quarter bucket from
`~/Documents/Claude/Projects/Thesis/04_RETROSPECTIVE_CASES/cohort_verified.md`
(§73–98). For each bucket, the protocol (§102–112) says: hand-pick 3
project-level candidates from Product Hunt / Indie Hackers archive / GitHub
trending / Substack directory in the matched quarter that have no public
evidence of crossing the §4.1 emergence threshold within 24 months.

The script is the canvas. Real handles + URLs live in the gitignored
`data/private/negative_peers_handles.csv` (see the .template for shape).
Only the anonymised `peer_id` ever crosses the public/private boundary.

Workflow (also in `scripts/README.md`):

  1. Open Product Hunt / IH archive / GH trending / Substack directory for
     the relevant quarter.
  2. Pick 3 candidates per niche; log URLs in the private CSV.
  3. Fill the corresponding `NegativePeer(...)` row below — `peer_id`,
     `public_signals_available`, `outcome_class`, and a 1-line `notes`
     summary. Replace `<PH URL or evidence>` with the summary.
  4. Run `python scripts/register_negative_peers.py` (idempotent —
     re-runnable as more peers are picked).
  5. Once ≥15 peers, run
     `python pipeline.py seed-labels eval backtest allocate`.

Slug convention: `NEG_<niche-slug>_<YYYYQX>_<NN>`. Niche-slug is the
kebab-case, lowercased niche label.

Allowed `outcome_class` values (from `ingestion/negative_peers.py`):
    "low_traction" | "no_launch" | "abandoned" | "drifted"
"""

from __future__ import annotations

from ingestion.negative_peers import (
    NegativePeer,
    materialise_for_outcome_labels,
    register_peer,
    write_protocol_summary,
)

_UNFILLED_NOTES = "<PH URL or evidence>"


PEERS: list[NegativePeer] = [
    # ------------------------------------------------------------------
    # 1. Indie SaaS — boilerplate / dev-tooling
    #    Matched positive: Marc Lou (ShipFast)
    #    Emergence quarter: 2023-Q3
    #    Search frame: Product Hunt Q3-2023 launches in dev-tooling that
    #                  did not cross $5k MRR / 10k followers in 24mo.
    # ------------------------------------------------------------------
    NegativePeer(
        peer_id="NEG_dev-tooling-boilerplate_2023Q3_01",  # TODO(kris): confirm slug
        matched_positive_niche="Indie SaaS — boilerplate / dev-tooling",
        matched_emergence_quarter="2023-Q3",
        public_signals_available=False,  # TODO(kris): set True/False after picking
        outcome_class="<FILL>",  # TODO(kris): low_traction | no_launch | abandoned | drifted
        notes=_UNFILLED_NOTES,  # TODO(kris): replace with 1-line summary + private-CSV row
    ),
    NegativePeer(
        peer_id="NEG_dev-tooling-boilerplate_2023Q3_02",  # TODO(kris)
        matched_positive_niche="Indie SaaS — boilerplate / dev-tooling",
        matched_emergence_quarter="2023-Q3",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_dev-tooling-boilerplate_2023Q3_03",  # TODO(kris)
        matched_positive_niche="Indie SaaS — boilerplate / dev-tooling",
        matched_emergence_quarter="2023-Q3",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    # ------------------------------------------------------------------
    # 2. Indie SaaS — image / video generation API
    #    Matched positive: Jon Yongfook (Bannerbear)
    #    Emergence quarter: 2020-Q4
    #    Search frame: Q4-2020 PH launches in image-gen / banner tools.
    # ------------------------------------------------------------------
    NegativePeer(
        peer_id="NEG_image-video-generation-api_2020Q4_01",  # TODO(kris)
        matched_positive_niche="Indie SaaS — image / video generation API",
        matched_emergence_quarter="2020-Q4",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_image-video-generation-api_2020Q4_02",  # TODO(kris)
        matched_positive_niche="Indie SaaS — image / video generation API",
        matched_emergence_quarter="2020-Q4",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_image-video-generation-api_2020Q4_03",  # TODO(kris)
        matched_positive_niche="Indie SaaS — image / video generation API",
        matched_emergence_quarter="2020-Q4",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    # ------------------------------------------------------------------
    # 3. Indie SaaS — Notion-adjacent tooling
    #    Matched positive: Noah Bragg (Potion)
    #    Emergence quarter: 2020-Q3
    #    Search frame: Q3-2020 Notion-extension launches.
    # ------------------------------------------------------------------
    NegativePeer(
        peer_id="NEG_notion-adjacent-tooling_2020Q3_01",  # TODO(kris)
        matched_positive_niche="Indie SaaS — Notion-adjacent tooling",
        matched_emergence_quarter="2020-Q3",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_notion-adjacent-tooling_2020Q3_02",  # TODO(kris)
        matched_positive_niche="Indie SaaS — Notion-adjacent tooling",
        matched_emergence_quarter="2020-Q3",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_notion-adjacent-tooling_2020Q3_03",  # TODO(kris)
        matched_positive_niche="Indie SaaS — Notion-adjacent tooling",
        matched_emergence_quarter="2020-Q3",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    # ------------------------------------------------------------------
    # 4. Indie SaaS — Twitter growth tools
    #    Matched positive: Thibault L-L + Tom J (Tweet Hunter)
    #    Emergence quarter: 2021-Q2
    #    Search frame: Q2-2021 Twitter-tools launches.
    # ------------------------------------------------------------------
    NegativePeer(
        peer_id="NEG_twitter-growth-tools_2021Q2_01",  # TODO(kris)
        matched_positive_niche="Indie SaaS — Twitter growth tools",
        matched_emergence_quarter="2021-Q2",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_twitter-growth-tools_2021Q2_02",  # TODO(kris)
        matched_positive_niche="Indie SaaS — Twitter growth tools",
        matched_emergence_quarter="2021-Q2",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_twitter-growth-tools_2021Q2_03",  # TODO(kris)
        matched_positive_niche="Indie SaaS — Twitter growth tools",
        matched_emergence_quarter="2021-Q2",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    # ------------------------------------------------------------------
    # 5. Indie SaaS — testimonials / social-proof
    #    Matched positive: Damon Chen (Testimonial.to)
    #    Emergence quarter: 2020-Q4
    #    Search frame: Q4-2020 testimonials / review tools.
    # ------------------------------------------------------------------
    NegativePeer(
        peer_id="NEG_testimonials-social-proof_2020Q4_01",  # TODO(kris)
        matched_positive_niche="Indie SaaS — testimonials / social-proof",
        matched_emergence_quarter="2020-Q4",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_testimonials-social-proof_2020Q4_02",  # TODO(kris)
        matched_positive_niche="Indie SaaS — testimonials / social-proof",
        matched_emergence_quarter="2020-Q4",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_testimonials-social-proof_2020Q4_03",  # TODO(kris)
        matched_positive_niche="Indie SaaS — testimonials / social-proof",
        matched_emergence_quarter="2020-Q4",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    # ------------------------------------------------------------------
    # 6. AI consumer / cheating tools
    #    Matched positive: Roy Lee (Cluely)
    #    Emergence quarter: 2025-Q2
    #    Search frame: Q2-2025 AI-augmented-productivity tools launched
    #                  on X / Product Hunt.
    # ------------------------------------------------------------------
    NegativePeer(
        peer_id="NEG_ai-consumer-cheating-tools_2025Q2_01",  # TODO(kris)
        matched_positive_niche="AI consumer / cheating tools",
        matched_emergence_quarter="2025-Q2",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_ai-consumer-cheating-tools_2025Q2_02",  # TODO(kris)
        matched_positive_niche="AI consumer / cheating tools",
        matched_emergence_quarter="2025-Q2",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_ai-consumer-cheating-tools_2025Q2_03",  # TODO(kris)
        matched_positive_niche="AI consumer / cheating tools",
        matched_emergence_quarter="2025-Q2",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    # ------------------------------------------------------------------
    # 7. AI creator-ads automation
    #    Matched positive: Simplr
    #    Emergence quarter: 2026-Q1
    #    Search frame: Q1-2026 creator-ads AI tools.
    #    Caveat: very recent — limited 24mo window for outcomes.
    # ------------------------------------------------------------------
    NegativePeer(
        peer_id="NEG_ai-creator-ads-automation_2026Q1_01",  # TODO(kris)
        matched_positive_niche="AI creator-ads automation",
        matched_emergence_quarter="2026-Q1",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_ai-creator-ads-automation_2026Q1_02",  # TODO(kris)
        matched_positive_niche="AI creator-ads automation",
        matched_emergence_quarter="2026-Q1",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_ai-creator-ads-automation_2026Q1_03",  # TODO(kris)
        matched_positive_niche="AI creator-ads automation",
        matched_emergence_quarter="2026-Q1",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    # ------------------------------------------------------------------
    # 8. Newsletter — vertical professional
    #    Matched positive: Lenny Rachitsky
    #    Emergence quarter: 2019-Q3
    #    Search frame: Q3-2019 Substack launches in product-management /
    #                  vertical professional niches.
    # ------------------------------------------------------------------
    NegativePeer(
        peer_id="NEG_newsletter-vertical-professional_2019Q3_01",  # TODO(kris)
        matched_positive_niche="Newsletter — vertical professional",
        matched_emergence_quarter="2019-Q3",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_newsletter-vertical-professional_2019Q3_02",  # TODO(kris)
        matched_positive_niche="Newsletter — vertical professional",
        matched_emergence_quarter="2019-Q3",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_newsletter-vertical-professional_2019Q3_03",  # TODO(kris)
        matched_positive_niche="Newsletter — vertical professional",
        matched_emergence_quarter="2019-Q3",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    # ------------------------------------------------------------------
    # 9. Newsletter — niche professional
    #    Matched positive: Monica Lent (Blogging for Devs)
    #    Emergence quarter: 2020-Q2
    #    Search frame: Q2-2020 dev-targeted newsletters.
    # ------------------------------------------------------------------
    NegativePeer(
        peer_id="NEG_newsletter-niche-professional_2020Q2_01",  # TODO(kris)
        matched_positive_niche="Newsletter — niche professional",
        matched_emergence_quarter="2020-Q2",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_newsletter-niche-professional_2020Q2_02",  # TODO(kris)
        matched_positive_niche="Newsletter — niche professional",
        matched_emergence_quarter="2020-Q2",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_newsletter-niche-professional_2020Q2_03",  # TODO(kris)
        matched_positive_niche="Newsletter — niche professional",
        matched_emergence_quarter="2020-Q2",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    # ------------------------------------------------------------------
    # 10. Newsletter / cohort writing
    #     Matched positive: Dickie Bush + Cole (Ship 30)
    #     Emergence quarter: 2020-Q3
    #     Search frame: Q3-2020 writing-cohort launches.
    # ------------------------------------------------------------------
    NegativePeer(
        peer_id="NEG_newsletter-cohort-writing_2020Q3_01",  # TODO(kris)
        matched_positive_niche="Newsletter / cohort writing",
        matched_emergence_quarter="2020-Q3",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_newsletter-cohort-writing_2020Q3_02",  # TODO(kris)
        matched_positive_niche="Newsletter / cohort writing",
        matched_emergence_quarter="2020-Q3",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_newsletter-cohort-writing_2020Q3_03",  # TODO(kris)
        matched_positive_niche="Newsletter / cohort writing",
        matched_emergence_quarter="2020-Q3",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    # ------------------------------------------------------------------
    # 11. Creator-economy education / finance
    #     Matched positive: Tori Dunlap (Her First 100K)
    #     Emergence quarter: 2021-Q2
    #     Search frame: Q2-2021 personal-finance creator launches.
    # ------------------------------------------------------------------
    NegativePeer(
        peer_id="NEG_creator-economy-education-finance_2021Q2_01",  # TODO(kris)
        matched_positive_niche="Creator-economy education / finance",
        matched_emergence_quarter="2021-Q2",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_creator-economy-education-finance_2021Q2_02",  # TODO(kris)
        matched_positive_niche="Creator-economy education / finance",
        matched_emergence_quarter="2021-Q2",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_creator-economy-education-finance_2021Q2_03",  # TODO(kris)
        matched_positive_niche="Creator-economy education / finance",
        matched_emergence_quarter="2021-Q2",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    # ------------------------------------------------------------------
    # 12. Solo-creator content business
    #     Matched positive: Justin Welsh
    #     Emergence quarter: 2022-Q1
    #     Search frame: Q1-2022 solopreneur content businesses on
    #                   LinkedIn / X.
    # ------------------------------------------------------------------
    NegativePeer(
        peer_id="NEG_solo-creator-content-business_2022Q1_01",  # TODO(kris)
        matched_positive_niche="Solo-creator content business",
        matched_emergence_quarter="2022-Q1",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_solo-creator-content-business_2022Q1_02",  # TODO(kris)
        matched_positive_niche="Solo-creator content business",
        matched_emergence_quarter="2022-Q1",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_solo-creator-content-business_2022Q1_03",  # TODO(kris)
        matched_positive_niche="Solo-creator content business",
        matched_emergence_quarter="2022-Q1",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    # ------------------------------------------------------------------
    # (Section 13 — Build-in-public indie portfolio / Pieter Levels —
    # SKIPPED per cohort_verified.md: "Use as the anchor case; n/a for
    # direct matching.")
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # 14. Community-led education
    #     Matched positive: Daniel Vassallo (Small Bets)
    #     Emergence quarter: 2021-Q4
    #     Search frame: Q4-2021 paid-community launches in
    #                   entrepreneurship.
    # ------------------------------------------------------------------
    NegativePeer(
        peer_id="NEG_community-led-education_2021Q4_01",  # TODO(kris)
        matched_positive_niche="Community-led education",
        matched_emergence_quarter="2021-Q4",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_community-led-education_2021Q4_02",  # TODO(kris)
        matched_positive_niche="Community-led education",
        matched_emergence_quarter="2021-Q4",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_community-led-education_2021Q4_03",  # TODO(kris)
        matched_positive_niche="Community-led education",
        matched_emergence_quarter="2021-Q4",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    # ------------------------------------------------------------------
    # 15. Mental models / behavioural-science newsletter
    #     Matched positive: Anne-Laure Le Cunff (Ness Labs)
    #     Emergence quarter: 2019-Q4
    #     Search frame: Q4-2019 behavioural-science / productivity
    #                   newsletters.
    # ------------------------------------------------------------------
    NegativePeer(
        peer_id="NEG_mental-models-newsletter_2019Q4_01",  # TODO(kris)
        matched_positive_niche="Mental models / behavioural-science newsletter",
        matched_emergence_quarter="2019-Q4",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_mental-models-newsletter_2019Q4_02",  # TODO(kris)
        matched_positive_niche="Mental models / behavioural-science newsletter",
        matched_emergence_quarter="2019-Q4",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_mental-models-newsletter_2019Q4_03",  # TODO(kris)
        matched_positive_niche="Mental models / behavioural-science newsletter",
        matched_emergence_quarter="2019-Q4",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    # ------------------------------------------------------------------
    # 16. Multi-product indie maker (Twitter tooling)
    #     Matched positive: Tony Dinh
    #     Emergence quarter: 2023-Q2
    #     Search frame: Q2-2023 X-creator tools.
    # ------------------------------------------------------------------
    NegativePeer(
        peer_id="NEG_multi-product-indie-twitter-tooling_2023Q2_01",  # TODO(kris)
        matched_positive_niche="Multi-product indie maker (Twitter tooling)",
        matched_emergence_quarter="2023-Q2",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_multi-product-indie-twitter-tooling_2023Q2_02",  # TODO(kris)
        matched_positive_niche="Multi-product indie maker (Twitter tooling)",
        matched_emergence_quarter="2023-Q2",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_multi-product-indie-twitter-tooling_2023Q2_03",  # TODO(kris)
        matched_positive_niche="Multi-product indie maker (Twitter tooling)",
        matched_emergence_quarter="2023-Q2",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    # ------------------------------------------------------------------
    # 17. Research-Substack — thematic equity / macro
    #     Matched positive: Citrini Research
    #     Emergence quarter: 2022-Q3
    #     Search frame: Q3-2022 finance/macro Substacks via Substack
    #                   directory; low-engagement filter.
    # ------------------------------------------------------------------
    NegativePeer(
        peer_id="NEG_research-substack-thematic-equity-macro_2022Q3_01",  # TODO(kris)
        matched_positive_niche="Research-Substack — thematic equity / macro",
        matched_emergence_quarter="2022-Q3",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_research-substack-thematic-equity-macro_2022Q3_02",  # TODO(kris)
        matched_positive_niche="Research-Substack — thematic equity / macro",
        matched_emergence_quarter="2022-Q3",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_research-substack-thematic-equity-macro_2022Q3_03",  # TODO(kris)
        matched_positive_niche="Research-Substack — thematic equity / macro",
        matched_emergence_quarter="2022-Q3",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    # ------------------------------------------------------------------
    # 18. Research-Substack — energy / commodities
    #     Matched positive: Doomberg
    #     Emergence quarter: 2021-Q2
    #     Search frame: Q2-2021 commodities / energy Substacks;
    #                   low-engagement filter.
    # ------------------------------------------------------------------
    NegativePeer(
        peer_id="NEG_research-substack-energy-commodities_2021Q2_01",  # TODO(kris)
        matched_positive_niche="Research-Substack — energy / commodities",
        matched_emergence_quarter="2021-Q2",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_research-substack-energy-commodities_2021Q2_02",  # TODO(kris)
        matched_positive_niche="Research-Substack — energy / commodities",
        matched_emergence_quarter="2021-Q2",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_research-substack-energy-commodities_2021Q2_03",  # TODO(kris)
        matched_positive_niche="Research-Substack — energy / commodities",
        matched_emergence_quarter="2021-Q2",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    # ------------------------------------------------------------------
    # 19. Research-Substack — tech / VC analyst
    #     Matched positive: Packy McCormick (Not Boring)
    #     Emergence quarter: 2020-Q4
    #     Search frame: Q4-2020 tech/VC Substack launches;
    #                   low-engagement filter.
    # ------------------------------------------------------------------
    NegativePeer(
        peer_id="NEG_research-substack-tech-vc-analyst_2020Q4_01",  # TODO(kris)
        matched_positive_niche="Research-Substack — tech / VC analyst",
        matched_emergence_quarter="2020-Q4",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_research-substack-tech-vc-analyst_2020Q4_02",  # TODO(kris)
        matched_positive_niche="Research-Substack — tech / VC analyst",
        matched_emergence_quarter="2020-Q4",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_research-substack-tech-vc-analyst_2020Q4_03",  # TODO(kris)
        matched_positive_niche="Research-Substack — tech / VC analyst",
        matched_emergence_quarter="2020-Q4",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    # ------------------------------------------------------------------
    # 20. Research-Substack — finance / tech analyst
    #     Matched positive: Byrne Hobart (The Diff)
    #     Emergence quarter: 2019-Q3
    #     Search frame: Q3-2019 finance/tech Substack launches;
    #                   low-engagement filter.
    # ------------------------------------------------------------------
    NegativePeer(
        peer_id="NEG_research-substack-finance-tech-analyst_2019Q3_01",  # TODO(kris)
        matched_positive_niche="Research-Substack — finance / tech analyst",
        matched_emergence_quarter="2019-Q3",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_research-substack-finance-tech-analyst_2019Q3_02",  # TODO(kris)
        matched_positive_niche="Research-Substack — finance / tech analyst",
        matched_emergence_quarter="2019-Q3",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
    NegativePeer(
        peer_id="NEG_research-substack-finance-tech-analyst_2019Q3_03",  # TODO(kris)
        matched_positive_niche="Research-Substack — finance / tech analyst",
        matched_emergence_quarter="2019-Q3",
        public_signals_available=False,  # TODO(kris)
        outcome_class="<FILL>",  # TODO(kris)
        notes=_UNFILLED_NOTES,  # TODO(kris)
    ),
]


def main() -> None:
    filled = [p for p in PEERS if p.notes != _UNFILLED_NOTES]
    stubs_remaining = len(PEERS) - len(filled)

    for peer in filled:
        register_peer(peer)

    print(
        f"registered {len(filled)} / {len(PEERS)} ({stubs_remaining} stubs remaining)"
    )

    if filled:
        materialise_for_outcome_labels()
        write_protocol_summary()


if __name__ == "__main__":
    main()
