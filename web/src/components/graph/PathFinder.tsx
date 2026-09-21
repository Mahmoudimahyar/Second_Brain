"use client";

/**
 * PathFinder — picker for two nodes + traversal depth + a "Find path"
 * button. Per 07-component-vocabulary.md §5.
 *
 * Stub-data path rendering; the actual subgraph traversal is wired in
 * V1.6 when the backend exposes `/api/v1/graph/path?from=...&to=...`.
 */

import { Route } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";

export interface PathFinderProps {
  onFind?: (from: string, to: string, depth: number) => void;
}

export function PathFinder({ onFind }: PathFinderProps) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [depth, setDepth] = useState(3);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Route className="size-4 text-info" />
          Find a path
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-xs">
        <div className="space-y-1">
          <Label htmlFor="path-from">From node ID</Label>
          <Input
            id="path-from"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            placeholder="school:nyu_dental"
            className="font-mono text-xs"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="path-to">To node ID</Label>
          <Input
            id="path-to"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            placeholder="post:predental:001"
            className="font-mono text-xs"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="path-depth">
            Max depth · <span className="font-mono">{depth}</span>
          </Label>
          <Slider
            id="path-depth"
            aria-label="Maximum traversal depth"
            min={1}
            max={6}
            step={1}
            value={[depth]}
            onValueChange={(v) => setDepth(v[0] ?? 3)}
          />
        </div>
        <Button
          size="sm"
          className="w-full"
          onClick={() => onFind?.(from, to, depth)}
          disabled={!from || !to}
        >
          Find path
        </Button>
      </CardContent>
    </Card>
  );
}
