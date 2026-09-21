"use client";

import { useMutation } from "@tanstack/react-query";
import { Upload as UploadIcon, X } from "lucide-react";
import { useRouter } from "next/navigation";
import {
  type ChangeEvent,
  type DragEvent,
  useCallback,
  useState,
} from "react";

import { Breadcrumbs } from "@/components/shared/Breadcrumbs";
import { ConnectionConfigForm } from "@/components/ingest/ConnectionConfigForm";
import { EngineIcon } from "@/components/ingest/EngineIcon";
import { TierSelector } from "@/components/ingest/TierSelector";
import { Button } from "@/components/ui/button";
import { sourcesApi } from "@/lib/api/client";
import type { SourceTier } from "@/components/shared/TierBadge";

const ACCEPTED = [".xlsx", ".pdf", ".csv", ".jsonl"];

interface QueuedFile {
  name: string;
  size: number;
  type: string;
  source_id: string;
}

function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/\.[^.]+$/, "")
    .replace(/[^a-z0-9_]/g, "_");
}

export default function NewUpload() {
  const router = useRouter();
  const [queued, setQueued] = useState<QueuedFile[]>([]);
  const [tier, setTier] = useState<SourceTier>("L2");
  const [confirmL1, setConfirmL1] = useState(false);
  const [hovered, setHovered] = useState(false);

  const addFiles = useCallback((files: FileList | File[]) => {
    const next: QueuedFile[] = [];
    for (const f of Array.from(files)) {
      const ext = f.name.toLowerCase().match(/\.[^.]+$/)?.[0] ?? "";
      if (!ACCEPTED.includes(ext)) continue;
      next.push({
        name: f.name,
        size: f.size,
        type: ext,
        source_id: `ds:upload:${slugify(f.name)}`,
      });
    }
    setQueued((q) => [...q, ...next]);
  }, []);

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setHovered(false);
    if (e.dataTransfer.files) addFiles(e.dataTransfer.files);
  };

  const onPick = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) addFiles(e.target.files);
  };

  const mutation = useMutation({
    mutationFn: async () => {
      const out: { source_id: string }[] = [];
      for (const f of queued) {
        const created = await sourcesApi.create({
          engine: "local_file",
          display_name: f.name,
          source_id: f.source_id,
          config: {
            file_name: f.name,
            file_type: f.type,
            file_size: f.size,
          },
          tier,
          confirm_l1_immutable: tier === "L1" ? confirmL1 : false,
        });
        out.push({ source_id: created.source_id });
      }
      return out;
    },
    onSuccess: (out) => {
      if (out[0]) {
        router.push(`/ingest/sources/${encodeURIComponent(out[0].source_id)}`);
      } else {
        router.push("/ingest");
      }
    },
  });

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <Breadcrumbs
        items={[
          { label: "Ingest", href: "/ingest" },
          { label: "New source", href: "/ingest/new" },
          { label: "Upload files" },
        ]}
      />
      <ConnectionConfigForm
        title="Upload files"
        description={`Each file becomes a LocalFileDataSource that routes through the V1 adapter for its type. Accepts ${ACCEPTED.join(", ")}.`}
        submitting={mutation.isPending}
        submitLabel={
          queued.length === 0
            ? "Add files first"
            : `Connect ${queued.length} file${queued.length === 1 ? "" : "s"}`
        }
        error={mutation.error ? (mutation.error as Error).message : null}
        onSubmit={() => queued.length > 0 && mutation.mutate()}
        preview={
          <div className="rounded-lg border border-border bg-surface/40 p-4 text-sm">
            <div className="flex items-center gap-2">
              <EngineIcon engine="upload" size="sm" />
              <h3 className="font-medium">Existing adapters reused</h3>
            </div>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-muted-foreground">
              <li>.xlsx → ADEA Excel adapter</li>
              <li>.pdf → SDE4 / L2 HTML adapter</li>
              <li>.csv → Generic table adapter</li>
              <li>.jsonl → Reddit / SDN adapter</li>
            </ul>
          </div>
        }
      >
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setHovered(true);
          }}
          onDragLeave={() => setHovered(false)}
          onDrop={onDrop}
          className={`rounded-lg border-2 border-dashed p-8 text-center text-sm transition-colors ${
            hovered
              ? "border-primary bg-primary/5"
              : "border-border bg-surface/40"
          }`}
          role="region"
          aria-label="File drop zone"
        >
          <UploadIcon
            className="mx-auto mb-2 size-8 text-muted-foreground"
            aria-hidden="true"
          />
          <p className="text-muted-foreground">Drag &amp; drop files here, or</p>
          <label className="mt-2 inline-block cursor-pointer">
            <span className="inline-flex h-9 items-center justify-center rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground hover:bg-primary/90">
              Choose files…
            </span>
            <input
              type="file"
              multiple
              accept={ACCEPTED.join(",")}
              onChange={onPick}
              className="hidden"
            />
          </label>
        </div>

        {queued.length > 0 && (
          <ul className="space-y-1 text-sm">
            {queued.map((f, i) => (
              <li
                key={`${f.name}:${i}`}
                className="flex items-center justify-between rounded-md border border-border bg-surface px-3 py-1.5"
              >
                <span className="min-w-0 truncate">{f.name}</span>
                <span className="ml-2 flex items-center gap-2">
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {f.type} · {(f.size / 1024).toFixed(1)} KB
                  </span>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    aria-label={`Remove ${f.name}`}
                    onClick={() => setQueued((q) => q.filter((_, j) => j !== i))}
                  >
                    <X className="size-3.5" />
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        )}

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
