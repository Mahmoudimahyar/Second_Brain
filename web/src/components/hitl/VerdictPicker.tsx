"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";

export type Verdict = "accept" | "reject" | "refine" | "defer";

const OPTIONS: {
  verdict: Verdict;
  label: string;
  variant: "default" | "destructive" | "secondary" | "ghost";
}[] = [
  { verdict: "accept", label: "Accept", variant: "default" },
  { verdict: "reject", label: "Reject", variant: "destructive" },
  { verdict: "refine", label: "Refine", variant: "secondary" },
  { verdict: "defer", label: "Defer", variant: "ghost" },
];

export interface VerdictPickerProps {
  onCommit: (verdict: Verdict, notes: string) => void;
  disabled?: boolean;
}

export function VerdictPicker({ onCommit, disabled }: VerdictPickerProps) {
  const [notes, setNotes] = useState("");
  return (
    <div className="space-y-2">
      <div>
        <Label htmlFor="hitl-notes">Reviewer notes</Label>
        <textarea
          id="hitl-notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Optional explanation for the next sweep…"
          rows={2}
          className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
          disabled={disabled}
        />
      </div>
      <div className="flex gap-2 flex-wrap" role="group" aria-label="Verdict actions">
        {OPTIONS.map((opt) => (
          <Button
            key={opt.verdict}
            variant={opt.variant}
            disabled={disabled}
            onClick={() => onCommit(opt.verdict, notes)}
          >
            {opt.label}
          </Button>
        ))}
      </div>
    </div>
  );
}
