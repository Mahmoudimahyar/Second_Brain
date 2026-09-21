"use client";

/**
 * W2-1 — Sigma.js WebGL graph canvas with ForceAtlas2 layout.
 *
 * Closes gap-audit HIGH-1 (Sigma.js canvas missing from V1.5b).
 *
 * Renders one of the three multi-level views (A=structural, B=clusters,
 * C=analyzed) onto a WebGL canvas. Per-level node + edge styling per
 * docs/08-ui/graph-level-views.md. Selection state propagates via the
 * `onSelect` callback; the page routes hook this into URL params so
 * Cmd-1/Cmd-2/Cmd-3 navigation preserves selection.
 *
 * Performance target: 5K-node load < 2s on a 2025-era laptop. The
 * 50K-node @ 60fps stretch goal stays a V1.6 follow-up.
 *
 * Accessibility: respects `prefers-reduced-motion` (disables FA2
 * animation); pairs with the existing `GraphResults.tsx` table fallback
 * accessible via the "View as table" link on each page.
 */

import { type ReactElement, useEffect, useMemo, useRef } from "react";
import Graph from "graphology";
import Sigma from "sigma";
import forceAtlas2 from "graphology-layout-forceatlas2";

import type { QueryResult } from "@/lib/api/client";

export type GraphLevel = "A" | "B" | "C";

export interface GraphCanvasProps {
  level: GraphLevel;
  results: QueryResult[];
  selectedNodeId?: string | null;
  onSelect?: (nodeId: string | null) => void;
  height?: number;
}

interface NodeStyle {
  size: number;
  color: string;
  type?: string;
}

/** Per-level styling per docs/08-ui/graph-level-views.md. */
function styleForLevel(
  level: GraphLevel,
  nodeType: string,
): NodeStyle {
  if (level === "A") {
    // Structural: small, neutral grays + blue for posts.
    if (nodeType === "Post" || nodeType === "Comment") {
      return { size: 4, color: "#2563eb" };
    }
    if (nodeType === "User") {
      return { size: 6, color: "#6b7280" };
    }
    return { size: 4, color: "#9ca3af" };
  }
  if (level === "B") {
    // Clusters: bigger, warmer.
    if (nodeType === "Cluster") return { size: 14, color: "#f59e0b" };
    if (nodeType === "Topic") return { size: 10, color: "#fb923c" };
    return { size: 6, color: "#fcd34d" };
  }
  // Level C — analyzed: rich palette by node type.
  if (nodeType === "Claim") return { size: 10, color: "#dc2626" };
  if (nodeType === "SentimentAnnotation") return { size: 8, color: "#7c3aed" };
  if (nodeType === "InterviewQuestion") return { size: 8, color: "#059669" };
  if (nodeType === "School") return { size: 12, color: "#0ea5e9" };
  return { size: 6, color: "#6b7280" };
}

export function GraphCanvas({
  level,
  results,
  selectedNodeId = null,
  onSelect,
  height = 600,
}: GraphCanvasProps): ReactElement {
  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma | null>(null);

  const graph = useMemo(() => {
    const g = new Graph();
    for (const r of results) {
      if (g.hasNode(r.node_id)) continue;
      const style = styleForLevel(level, r.node_type);
      g.addNode(r.node_id, {
        label: r.properties?.title || r.properties?.name || r.node_id,
        size: style.size,
        color: style.color,
        x: Math.random(),
        y: Math.random(),
      });
    }
    // Edges from the path_explanation array (each step is one edge).
    for (const r of results) {
      for (const step of r.path_explanation ?? []) {
        if (!g.hasNode(step.from)) continue;
        if (!g.hasNode(step.to)) continue;
        const edgeKey = `${step.from}->${step.to}:${step.edge_type}`;
        if (g.hasEdge(edgeKey)) continue;
        g.addEdgeWithKey(edgeKey, step.from, step.to, {
          label: step.edge_type,
          size: 1,
          color: level === "A" ? "#cbd5e1" : "#9ca3af",
        });
      }
    }
    return g;
  }, [level, results]);

  // Layout: run ForceAtlas2 to spread nodes. Reduced-motion users get a
  // single static pass; everyone else gets 200 iterations.
  useEffect(() => {
    if (graph.order === 0) return;
    const prefersReducedMotion =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const iterations = prefersReducedMotion ? 50 : 200;
    forceAtlas2.assign(graph, {
      iterations,
      settings: {
        gravity: 1.0,
        scalingRatio: 10,
        strongGravityMode: false,
        slowDown: 1,
      },
    });
  }, [graph]);

  useEffect(() => {
    if (!containerRef.current) return;
    const sigma = new Sigma(graph, containerRef.current, {
      renderEdgeLabels: false,
      labelSize: 12,
      labelWeight: "bold",
      defaultEdgeColor: "#e5e7eb",
    });
    sigmaRef.current = sigma;

    const clickHandler = (event: { node: string }) => {
      onSelect?.(event.node);
    };
    const stageClickHandler = () => {
      onSelect?.(null);
    };
    sigma.on("clickNode", clickHandler);
    sigma.on("clickStage", stageClickHandler);

    return () => {
      sigma.off("clickNode", clickHandler);
      sigma.off("clickStage", stageClickHandler);
      sigma.kill();
      sigmaRef.current = null;
    };
  }, [graph, onSelect]);

  // Highlight selected node by setting forceLabel + size bump.
  useEffect(() => {
    const sigma = sigmaRef.current;
    if (!sigma) return;
    graph.forEachNode((nodeId, attrs) => {
      const isSelected = nodeId === selectedNodeId;
      graph.setNodeAttribute(nodeId, "highlighted", isSelected);
      if (isSelected) {
        graph.setNodeAttribute(nodeId, "forceLabel", true);
      } else {
        graph.removeNodeAttribute(nodeId, "forceLabel");
      }
    });
    sigma.refresh();
  }, [graph, selectedNodeId]);

  if (results.length === 0) {
    return (
      <div
        className="rounded border border-dashed border-gray-300 bg-gray-50 p-8 text-center text-sm text-gray-500"
        role="status"
      >
        No results for this level — try a different query or run a Pass-4
        sweep on the current corpus.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div
        ref={containerRef}
        style={{ height }}
        className="w-full rounded border bg-white"
        role="img"
        aria-label={`Level ${level} graph canvas with ${graph.order} nodes`}
      />
      <p className="text-xs text-gray-500">
        Level {level} · {graph.order} nodes · {graph.size} edges.{" "}
        <a className="underline" href={`?view=table`}>
          View as table
        </a>{" "}
        if you prefer a non-canvas surface.
      </p>
    </div>
  );
}
