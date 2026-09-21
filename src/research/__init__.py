"""Research protocol — turn insight questions into measured estimates with uncertainty,
robustness, temporal analysis, bias labelling, and provenance.

Every answer routes through `EvidenceDossierEngine.research()` (see `protocol.py`), which
applies the same lab protocol regardless of question:

  estimand + denominator -> retrieve -> classify -> enrich (thread/author/year/cohort) ->
  estimate + thread-clustered CI -> shrinkage (rankings) -> measurement-error sensitivity
  -> robustness sweep -> temporal trend -> bias label -> provenance -> quality score.
"""
