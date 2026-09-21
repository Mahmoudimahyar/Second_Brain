"""V1.5c per-team aggregation backends.

Three teams:
- `pm`: pain points → suggested feature angles
- `social`: trending topics → suggested post angles
- `marketing`: content gaps → suggested content angles

Each ships a `compute_*` function + a `suggest_angles` entry point that
routes through the model gateway with task `team_content_angles`.
"""

from src.teams.angles import suggest_angles
from src.teams.marketing import ContentGap, compute_content_gaps
from src.teams.pm import PainPoint, compute_pain_points
from src.teams.social import TrendingTopic, compute_trending_topics

__all__ = [
    "ContentGap",
    "PainPoint",
    "TrendingTopic",
    "compute_content_gaps",
    "compute_pain_points",
    "compute_trending_topics",
    "suggest_angles",
]
