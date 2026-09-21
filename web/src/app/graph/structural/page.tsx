import { GraphViewPage } from "@/components/graph/GraphViewPage";

export default function GraphStructural() {
  return (
    <GraphViewPage
      level="A"
      title="Graph · Level A (structural)"
      description="Deterministic Pass-1 subgraph: users, posts, comments, threads."
    />
  );
}
