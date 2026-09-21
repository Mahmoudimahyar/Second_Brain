"""M3 concept criteria — the externally-researched definition of an abstract concept,
cached so the engine can apply it (the engine can't web-search at query time; the deep
research is an offline refresh that produces this artifact, with sources for provenance).

Each criterion maps to a computable corpus signal (see signals.py) + a weight + the
rationale and source it came from. The concept path scores topics by the weighted,
normalized signals. Override the defaults with `<bundle>/concept_criteria.json`.
"""

from __future__ import annotations

import json
from pathlib import Path

# Seeded from a web deep-research pass (2026-06-22): Berger & Milkman virality research +
# 2025-26 TikTok/Instagram ranking signals + what works for dental/pre-health creators.
DEFAULT_CRITERIA: dict = {
    "virality": {
        "description": "Propensity of a topic's content to be shared on social platforms.",
        "researched_date": "2026-06-22",
        "sources": [
            "https://journals.sagepub.com/doi/abs/10.1509/jmr.10.0353",   # Berger & Milkman 2012
            "https://pageblock.io/resources/framework/stepps",            # STEPPS
            "https://blog.hootsuite.com/tiktok-algorithm/",               # TikTok 2026 signals
            "https://almcorp.com/blog/instagram-algorithm-update-december-2025/",
            "https://www.remedo.io/blog/how-dentists-can-become-influencers-on-tiktok-instagram",
        ],
        "keywords": ["viral", "go viral", "shareable", "share", "engaging", "engagement",
                     "resonate", "resonates", "most popular posts", "social media post"],
        "criteria": [
            {"name": "high_arousal_emotion", "signal": "emotion_intensity", "weight": 0.30,
             "rationale": "Berger & Milkman: high-arousal emotion (awe, anger, anxiety, "
                          "humor) drives sharing; low-arousal (sadness) does not."},
            {"name": "shareability_engagement", "signal": "engagement_score", "weight": 0.20,
             "rationale": "2025-26 platforms weight shares/saves above likes; our proxy is "
                          "p90 comment score (forum engagement)."},
            {"name": "practical_value", "signal": "advice_density", "weight": 0.20,
             "rationale": "STEPPS Practical Value; saveable how-to content is favored by the "
                          "2025 algorithms."},
            {"name": "stories", "signal": "narrative_density", "weight": 0.15,
             "rationale": "STEPPS Stories; personal experience / behind-the-scenes is what "
                          "works for pre-health creators."},
            {"name": "social_currency", "signal": "social_currency", "weight": 0.15,
             "rationale": "STEPPS Social Currency; status/achievement (acceptances, stats) "
                          "makes sharers look good."},
        ],
        "caveat": "Forum sentiment/score/text are PROXIES for virality — we do not have "
                  "Instagram/TikTok reach. This ranks share-propensity properties of each "
                  "topic, not measured platform virality.",
    },
    "seo": {
        "description": "Organic search / SEO value of a blog topic.",
        "researched_date": "2026-06-22",
        "sources": [
            "https://dentalmarketingbff.com/dental-seo/content-marketing/blog-post-ideas/",
            "https://www.remedo.io/blog/keyword-research-tips-for-dentists",
            "https://whitehat-seo.co.uk/blog/dental-content-marketing-aeo",
            "https://www.firegang.com/keyword-research-for-dentists/",
        ],
        "keywords": ["seo", "search engine", "blog post", "blog", "organic search",
                     "rank on google", "google search", "search ranking"],
        "criteria": [
            {"name": "search_demand", "signal": "demand_pct", "weight": 0.35,
             "rationale": "Forum question volume proxies search demand — SEO sources note "
                          "Reddit/Quora questions reveal exactly what searchers ask."},
            {"name": "informational_intent", "signal": "advice_density", "weight": 0.30,
             "rationale": "How/why/what question content = informational queries, the blog "
                          "sweet spot for ranking + topical authority."},
            {"name": "evergreen", "signal": "recency", "weight": 0.20,
             "rationale": "Topics still active across recent years = evergreen traffic "
                          "magnets (60-70% of recommended SEO content)."},
            {"name": "engagement", "signal": "engagement_score", "weight": 0.15,
             "rationale": "Engagement proxies sustained topical interest."},
        ],
        "caveat": "Search demand is proxied by FORUM discussion volume, not Google Keyword "
                  "Planner volume — validate top picks with a real keyword tool "
                  "(Ubersuggest / AnswerThePublic) and check keyword difficulty before "
                  "committing. YMYL/E-E-A-T: dental content needs author expertise signals.",
    },
}


class ConceptCriteria:
    """Loads concept criteria (bundle override -> packaged defaults)."""

    def __init__(self, bundle_path: str | Path | None = None) -> None:
        self.data = dict(DEFAULT_CRITERIA)
        if bundle_path:
            p = Path(bundle_path) / "concept_criteria.json"
            if p.exists():
                try:
                    self.data.update(json.loads(p.read_text()))
                except (json.JSONDecodeError, OSError):
                    pass

    def get(self, concept: str) -> dict | None:
        return self.data.get(concept)

    def detect(self, question: str) -> str | None:
        """Which researched concept (if any) does the question invoke?"""
        q = (question or "").lower()
        for concept, spec in self.data.items():
            if any(kw in q for kw in spec.get("keywords", [])):
                return concept
        return None

    def signal_keys(self, concept: str) -> list[str]:
        spec = self.data.get(concept) or {}
        return [c["signal"] for c in spec.get("criteria", [])]
