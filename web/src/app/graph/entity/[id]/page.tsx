"use client";

/**
 * /graph/entity/[id] — deep-link landing. Lifts the GraphViewPage
 * scoped to a single entity (URL ?query=ID is the same Level C
 * canvas behavior).
 */

import { use, useEffect } from "react";
import { useRouter } from "next/navigation";

import { Breadcrumbs } from "@/components/shared/Breadcrumbs";
import { LoadingState } from "@/components/shared/LoadingState";

export default function GraphEntityRedirect({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  useEffect(() => {
    router.replace(`/graph/analyzed?query=${encodeURIComponent(id)}`);
  }, [id, router]);
  return (
    <div className="space-y-4">
      <Breadcrumbs
        items={[
          { label: "Graph", href: "/graph/analyzed" },
          { label: "Entity" },
          { label: id },
        ]}
      />
      <LoadingState variant="graph" />
    </div>
  );
}
