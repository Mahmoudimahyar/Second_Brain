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

export default function NewMySQL() {
  const router = useRouter();
  const [form, setForm] = useState({
    display_name: "Partner MySQL",
    source_id: "ds:mysql:partner",
    host: "localhost",
    port: 3306,
    database: "",
    user: "",
    schema_filter: "",
    ssl: false,
  });
  const [credentialRef, setCredentialRef] = useState("PARTNER_MYSQL_PASSWORD");
  const [tier, setTier] = useState<SourceTier>("L2");
  const [confirmL1, setConfirmL1] = useState(false);

  const mutation = useMutation({
    mutationFn: async () => {
      const sf = form.schema_filter.split(",").map((s) => s.trim()).filter(Boolean);
      return sourcesApi.create({
        engine: "mysql",
        display_name: form.display_name,
        source_id: form.source_id,
        config: {
          host: form.host,
          port: form.port,
          database: form.database,
          user: form.user,
          ssl: form.ssl,
          ...(sf.length ? { schema_filter: sf } : {}),
        },
        credential_ref: credentialRef,
        tier,
        confirm_l1_immutable: tier === "L1" ? confirmL1 : false,
      });
    },
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
          { label: "MySQL" },
        ]}
      />
      <ConnectionConfigForm
        title="Connect MySQL"
        description="Read-only role recommended. Default port 3306."
        submitting={mutation.isPending}
        submitLabel="Test connection + continue"
        error={mutation.error ? (mutation.error as Error).message : null}
        onSubmit={() => mutation.mutate()}
        preview={
          <div className="rounded-lg border border-border bg-surface/40 p-4 text-sm">
            <div className="flex items-center gap-2">
              <EngineIcon engine="mysql" size="sm" />
              <h3 className="font-medium">MySQL connector notes</h3>
            </div>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-muted-foreground">
              <li>UTF-8 (utf8mb4) recommended.</li>
              <li>Empty schema filter pulls every visible schema.</li>
              <li>Foreign-key DAG used for mapping suggestions.</li>
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
          <div className="space-y-1.5">
            <Label htmlFor="host">Host</Label>
            <Input
              id="host"
              required
              value={form.host}
              onChange={(e) => setForm({ ...form, host: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="port">Port</Label>
            <Input
              id="port"
              type="number"
              required
              value={form.port}
              onChange={(e) => setForm({ ...form, port: Number(e.target.value) })}
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
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="schema_filter">Schema filter (comma-separated)</Label>
            <Input
              id="schema_filter"
              value={form.schema_filter}
              onChange={(e) => setForm({ ...form, schema_filter: e.target.value })}
              placeholder="e.g. billing, marketing"
            />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-4 accent-primary"
              checked={form.ssl}
              onChange={(e) => setForm({ ...form, ssl: e.target.checked })}
            />
            <span>Require SSL</span>
          </label>
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
