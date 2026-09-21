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

const PREVIEW_STEPS = [
  "List your tables and sample 100 rows each.",
  "Suggest how each table maps to a Node or Edge.",
  "You approve mappings (high-conf auto, low-conf reviewed).",
  "Pull deltas on the schedule (default daily).",
];

export default function NewPostgres() {
  const router = useRouter();
  const [form, setForm] = useState({
    display_name: "Partner Postgres",
    source_id: "ds:postgres:partner",
    host: "localhost",
    port: 5432,
    database: "",
    user: "",
    ssl_mode: "prefer",
    schema_filter: "public",
  });
  const [credentialRef, setCredentialRef] = useState("PARTNER_DB_PASSWORD");
  const [tier, setTier] = useState<SourceTier>("L2");
  const [confirmL1, setConfirmL1] = useState(false);

  const mutation = useMutation({
    mutationFn: async () =>
      sourcesApi.create({
        engine: "postgres",
        display_name: form.display_name,
        source_id: form.source_id,
        config: {
          host: form.host,
          port: form.port,
          database: form.database,
          user: form.user,
          ssl_mode: form.ssl_mode,
          schema_filter: form.schema_filter,
        },
        credential_ref: credentialRef,
        tier,
        confirm_l1_immutable: tier === "L1" ? confirmL1 : false,
      }),
    onSuccess: () => {
      router.push(`/ingest/sources/${encodeURIComponent(form.source_id)}`);
    },
  });

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <Breadcrumbs
        items={[
          { label: "Ingest", href: "/ingest" },
          { label: "New source", href: "/ingest/new" },
          { label: "PostgreSQL" },
        ]}
      />
      <ConnectionConfigForm
        title="Connect PostgreSQL"
        description="Read-only role recommended. We sample 100 rows per table for the discovery preview."
        submitting={mutation.isPending}
        submitLabel="Test connection + continue"
        error={mutation.error ? (mutation.error as Error).message : null}
        onSubmit={() => mutation.mutate()}
        preview={
          <PreviewPanel
            heading="What this connector will do"
            steps={PREVIEW_STEPS}
            footer="Est. time: ~2 min for a typical 50-table DB."
          />
        }
      >
        <FieldGrid>
          <Field id="display_name" label="Display name">
            <Input
              id="display_name"
              required
              value={form.display_name}
              onChange={(e) => setForm({ ...form, display_name: e.target.value })}
            />
          </Field>
          <Field id="source_id" label="Source ID">
            <Input
              id="source_id"
              required
              className="font-mono text-xs"
              value={form.source_id}
              onChange={(e) => setForm({ ...form, source_id: e.target.value })}
            />
          </Field>
          <Field id="host" label="Host">
            <Input
              id="host"
              required
              value={form.host}
              onChange={(e) => setForm({ ...form, host: e.target.value })}
            />
          </Field>
          <Field id="port" label="Port">
            <Input
              id="port"
              type="number"
              required
              value={form.port}
              onChange={(e) => setForm({ ...form, port: Number(e.target.value) })}
            />
          </Field>
          <Field id="database" label="Database">
            <Input
              id="database"
              required
              value={form.database}
              onChange={(e) => setForm({ ...form, database: e.target.value })}
            />
          </Field>
          <Field id="user" label="User">
            <Input
              id="user"
              required
              value={form.user}
              onChange={(e) => setForm({ ...form, user: e.target.value })}
            />
          </Field>
          <Field id="ssl_mode" label="SSL mode">
            <Input
              id="ssl_mode"
              value={form.ssl_mode}
              onChange={(e) => setForm({ ...form, ssl_mode: e.target.value })}
            />
          </Field>
          <Field id="schema_filter" label="Schema filter">
            <Input
              id="schema_filter"
              value={form.schema_filter}
              onChange={(e) => setForm({ ...form, schema_filter: e.target.value })}
            />
          </Field>
        </FieldGrid>

        <CredentialField
          envVarRef={credentialRef}
          onEnvVarRefChange={setCredentialRef}
          helpText="The Postgres driver reads the env var at connection time."
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

function FieldGrid({ children }: { children: React.ReactNode }) {
  return <div className="grid gap-4 sm:grid-cols-2">{children}</div>;
}

function Field({
  id,
  label,
  children,
}: {
  id: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}

function PreviewPanel({
  heading,
  steps,
  footer,
}: {
  heading: string;
  steps: string[];
  footer?: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-surface/40 p-4 text-sm">
      <div className="flex items-center gap-2">
        <EngineIcon engine="postgres" size="sm" />
        <h3 className="font-medium">{heading}</h3>
      </div>
      <ol className="mt-2 list-decimal space-y-1 pl-5 text-muted-foreground">
        {steps.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ol>
      {footer && <p className="mt-3 text-xs text-muted-foreground">{footer}</p>}
    </div>
  );
}
