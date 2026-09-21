"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Breadcrumbs } from "@/components/shared/Breadcrumbs";
import { ConnectionConfigForm } from "@/components/ingest/ConnectionConfigForm";
import { CredentialField } from "@/components/ingest/CredentialField";
import { EngineIcon } from "@/components/ingest/EngineIcon";
import { TierSelector } from "@/components/ingest/TierSelector";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { sourcesApi } from "@/lib/api/client";
import type { SourceTier } from "@/components/shared/TierBadge";

export default function NewNeo4j() {
  const router = useRouter();
  const [form, setForm] = useState({
    display_name: "Partner Neo4j",
    source_id: "ds:neo4j:partner",
    uri: "bolt://localhost:7687",
    database: "neo4j",
    user: "neo4j",
  });
  const [credentialRef, setCredentialRef] = useState("PARTNER_NEO4J_PASSWORD");
  const [tier, setTier] = useState<SourceTier>("L2");
  const [confirmL1, setConfirmL1] = useState(false);

  const mutation = useMutation({
    mutationFn: async () =>
      sourcesApi.create({
        engine: "neo4j",
        display_name: form.display_name,
        source_id: form.source_id,
        config: {
          uri: form.uri,
          database: form.database,
          user: form.user,
        },
        credential_ref: credentialRef,
        tier,
        confirm_l1_immutable: tier === "L1" ? confirmL1 : false,
      }),
    onSuccess: () =>
      router.push(`/ingest/sources/${encodeURIComponent(form.source_id)}`),
  });

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <Breadcrumbs
        items={[
          { label: "Ingest", href: "/ingest" },
          { label: "New source", href: "/ingest/new" },
          { label: "Neo4j" },
        ]}
      />
      <ConnectionConfigForm
        title="Connect Neo4j"
        description="Bolt protocol. Discovery returns node labels + relationship types."
        submitting={mutation.isPending}
        submitLabel="Test connection + continue"
        error={mutation.error ? (mutation.error as Error).message : null}
        onSubmit={() => mutation.mutate()}
        preview={
          <div className="rounded-lg border border-border bg-surface/40 p-4 text-sm">
            <div className="flex items-center gap-2">
              <EngineIcon engine="neo4j" size="sm" />
              <h3 className="font-medium">Neo4j notes</h3>
            </div>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-muted-foreground">
              <li>Cross-graph linking maps Neo4j labels to V1 entity types.</li>
              <li>Per-label sampling: 50 nodes + 50 outbound edges per label.</li>
              <li>Default DB `neo4j` unless overridden.</li>
            </ul>
          </div>
        }
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="display_name">Display name</Label>
            <Input
              id="display_name"
              required
              value={form.display_name}
              onChange={(e) => setForm({ ...form, display_name: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="source_id">Source ID</Label>
            <Input
              id="source_id"
              required
              className="font-mono text-xs"
              value={form.source_id}
              onChange={(e) => setForm({ ...form, source_id: e.target.value })}
            />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="uri">Bolt URI</Label>
            <Input
              id="uri"
              required
              className="font-mono text-xs"
              value={form.uri}
              onChange={(e) => setForm({ ...form, uri: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="database">Database</Label>
            <Input
              id="database"
              required
              value={form.database}
              onChange={(e) => setForm({ ...form, database: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="user">User</Label>
            <Input
              id="user"
              required
              value={form.user}
              onChange={(e) => setForm({ ...form, user: e.target.value })}
            />
          </div>
        </div>
        <CredentialField
          envVarRef={credentialRef}
          onEnvVarRefChange={setCredentialRef}
        />
        <TierSelector
          value={tier}
          onChange={setTier}
          confirmL1={confirmL1}
          onConfirmL1Change={setConfirmL1}
        />
      </ConnectionConfigForm>
    </div>
  );
}
