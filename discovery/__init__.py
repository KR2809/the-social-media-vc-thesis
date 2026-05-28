"""Forward-looking topic + candidate discovery.

Wraps `analysis.topic_discovery` (which does Pass A cohort ranking + Pass B
pytrends rising) with:

  - LLM clustering of seed topics into 5–15 coherent thematic groups,
  - Cross-platform candidate-handle harvesting (Reddit, Hacker News),
  - A ranked candidate slate per cluster suitable for piping into
    `ranking.rank_handles`.

The frontend (Stream D) is responsible for the "discover → review → rank"
UX — this layer never auto-triggers ranking, only produces the slate.
"""
