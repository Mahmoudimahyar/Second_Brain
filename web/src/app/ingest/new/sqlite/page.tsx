"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Breadcrumbs } from "@/components/shared/Breadcrumbs";
import { ConnectionConfigForm } from "@/components/ingest/ConnectionConfigForm";
import { EngineIcon } from "@/components/ingest/EngineIcon";
import { TierSelector } from "@/components/ingest/TierSelector";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { sourcesApi } from "@/lib/api/client";
import type { SourceTier } from "@/components/shared/TierBadge";

export default function NewSQLite() {
  const router = useRouter();
  const [form, setForm] = useState({
    display_name: "Local SQLite",
    source_id: "ds:sqlite:local",
    file_path: "",
  });
  const [tier, setTier] = useState<SourceTier>("L2");
  const [confirmL1, setConfirmL1] = useState(false);

  const mutation = useMutation({
    mutationFn: async () =>
      sourcesApi.create({
        engine: "sqlite",
        display_name: form.display_name,
        source_id: form.source_id,
        config: { file_path: form.file_path },
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
          { label: "SQLite" },
        ]}
      />
      <ConnectionConfigForm
        title="Connect SQLite"
        description="Point at a `.sqlite` / `.db` file on the SecBrain process's filesystem."
        submitting={mutation.isPending}
        submitLabel="Continue"
        error={mutation.error ? (mutation.error as Error).message : null}
        onSubmit={() => mutation.mutate()}
        preview={
          <div className="rounded-lg border border-border bg-surface/40 p-4 text-sm">
            <div className="flex items-center gap-2">
              <EngineIcon engine="sqlite" size="sm" />
              <h3 className="font-medium">SQLite notes</h3>
            </div>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-muted-foreground">
              <li>Read-only open; no schema mutations performed.</li>
              <li>Best engine for the V1 seed corpus + ADEA SQL dumps.</li>
              <li>No credential required — file is read with process permissions.</li>
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
            <Label htmlFor="file_path">SQLite file path</Label>
            <Input
              id="file_path"
              required
              className="font-mono text-xs"
              value={form.file_path}
              onChange={(e) => setForm({ ...form, file_path: e.target.value })}
              placeholder="C:\path\to\adea.sqlite"
            />
          </div>
        </div>
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
