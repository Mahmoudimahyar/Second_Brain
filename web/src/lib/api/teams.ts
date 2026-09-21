/**
 * V1.5c — Team dashboard API client.
 */

const BASE = process.env.NEXT_PUBLIC_API_BASE || "";

async function req<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}/api/v1${path}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { message?: string }).message || res.statusText);
  }
  return res.json() as Promise<T>;
}

export type TrendBucket = {
  /** ISO date (YYYY-MM-DD). */
  date: string;
  volume: number;
  avg_sentiment: number;
};

export type PainPoint = {
  pain_point_id: string;
  title: string;
  audience_segment: string;
  volume: number;
  avg_sentiment: number;
  references: string[];
  /** Last-N day series (empty when no input row carried a timestamp). */
  daily_buckets?: TrendBucket[];
  /** Per-tier evidence fractions (empty when no input row carried a tier). */
  tier_mix?: Record<string, number>;
};

export type ClusterContribution = {
  cluster_id: string;
  label: string;
  count: number;
};

export type TrendingTopic = {
  topic_id: string;
  name: string;
  window_volume: number;
  baseline_volume?: number;
  trend_ratio: number;
  avg_sentiment: number;
  references: string[];
  /** Per-day buckets within the trending window. */
  daily_buckets?: TrendBucket[];
};

export type ContentGap = {
  gap_id: string;
  topic: string;
  volume: number;
  avg_sentiment: number;
  gap_severity: number;
  references: string[];
  sample_excerpts?: string[];
};

export type SuggestedAngle = {
  angle: string;
  rationale: string;
  citations: string[];
  draft_only: boolean;
};

export const teamsApi = {
  pm: () => req<{ pain_points: PainPoint[] }>("/teams/pm"),
  pmDetail: (id: string) =>
    req<{
      pain_point: PainPoint;
      top_clusters: ClusterContribution[];
      suggested_angles: SuggestedAngle[];
    }>(`/teams/pm/${encodeURIComponent(id)}`),
  social: () => req<{ trends: TrendingTopic[] }>("/teams/social"),
  socialTopic: (id: string) =>
    req<{ topic: TrendingTopic; suggested_angles: SuggestedAngle[] }>(
      `/teams/social/topic/${encodeURIComponent(id)}`,
    ),
  marketing: () => req<{ gaps: ContentGap[] }>("/teams/marketing"),
  marketingGap: (id: string) =>
    req<{ gap: ContentGap; suggested_angles: SuggestedAngle[] }>(
      `/teams/marketing/gap/${encodeURIComponent(id)}`,
    ),
};
