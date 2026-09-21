"use client";

/**
 * TrendingTopicCarousel — embla-powered horizontal scroller per
 * 07-component-vocabulary.md §6.
 */

import useEmblaCarousel from "embla-carousel-react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback } from "react";

import { MiniSparkline } from "@/components/team/MiniSparkline";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export interface TrendingTopicCard {
  topic_id: string;
  name: string;
  trend_ratio: number;
  trend?: number[];
  window_volume: number;
}

export interface TrendingTopicCarouselProps {
  topics: TrendingTopicCard[];
  onPick?: (topicId: string) => void;
}

export function TrendingTopicCarousel({
  topics,
  onPick,
}: TrendingTopicCarouselProps) {
  const [emblaRef, embla] = useEmblaCarousel({ align: "start", loop: false });
  const prev = useCallback(() => embla?.scrollPrev(), [embla]);
  const next = useCallback(() => embla?.scrollNext(), [embla]);

  if (topics.length === 0) {
    return null;
  }

  return (
    <section
      className="relative"
      aria-label="Trending topics carousel"
    >
      <header className="mb-2 flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Carousel
        </p>
        <div className="flex gap-1">
          <Button
            variant="ghost"
            size="icon"
            onClick={prev}
            aria-label="Scroll previous"
            className="h-7 w-7"
          >
            <ChevronLeft className="size-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={next}
            aria-label="Scroll next"
            className="h-7 w-7"
          >
            <ChevronRight className="size-3.5" />
          </Button>
        </div>
      </header>

      <div className="overflow-hidden" ref={emblaRef}>
        <ul className="flex gap-3">
          {topics.map((t) => (
            <li key={t.topic_id} className="min-w-[220px] flex-none">
              <button
                type="button"
                onClick={() => onPick?.(t.topic_id)}
                className="block w-full text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                <Card className="transition-shadow hover:shadow-md">
                  <CardContent className="space-y-2 p-3">
                    <div className="flex items-center justify-between">
                      <h4 className="truncate text-sm font-semibold">
                        {t.name}
                      </h4>
                      <Badge
                        variant={t.trend_ratio >= 2 ? "warning" : "secondary"}
                        className="font-mono text-[10px]"
                      >
                        {t.trend_ratio.toFixed(1)}×
                      </Badge>
                    </div>
                    {t.trend && t.trend.length > 0 && (
                      <MiniSparkline values={t.trend} width={196} height={28} />
                    )}
                    <p className="font-mono text-[10px] text-muted-foreground">
                      {t.window_volume} mentions
                    </p>
                  </CardContent>
                </Card>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
