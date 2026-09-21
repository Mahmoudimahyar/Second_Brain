"use client";

/**
 * CursorEditor — power-user override for the per-table cursor column
 * per 07-component-vocabulary.md §3. Lets the operator pick which
 * column the delta-pull uses + reset the saved high-water mark.
 */

import { RotateCcw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export interface CursorRow {
  table: string;
  column: string;
  high_water_mark: string | null;
}

export interface CursorEditorProps {
  cursors: CursorRow[];
  onChange?: (idx: number, next: CursorRow) => void;
  onReset?: (idx: number) => void;
}

export function CursorEditor({ cursors, onChange, onReset }: CursorEditorProps) {
  if (cursors.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        Cursors materialize after the first pull. None tracked yet.
      </p>
    );
  }
  return (
    <Card>
      <CardContent className="space-y-3 p-4 text-sm">
        <p className="text-[11px] text-muted-foreground">
          Power-user controls. Edit the cursor column or reset the
          high-water mark to force a full re-pull on the next sweep.
        </p>
        <ul className="space-y-2">
          {cursors.map((c, i) => (
            <li
              key={c.table}
              className="grid items-center gap-2 sm:grid-cols-[1fr_1fr_1fr_auto]"
            >
              <Badge variant="outline" className="font-mono text-[10px]">
                {c.table}
              </Badge>
              <div className="space-y-0.5">
                <Label htmlFor={`col-${i}`} className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  Cursor column
                </Label>
                <Input
                  id={`col-${i}`}
                  value={c.column}
                  onChange={(e) => onChange?.(i, { ...c, column: e.target.value })}
                  className="h-7 font-mono text-xs"
                />
              </div>
              <div className="space-y-0.5">
                <Label htmlFor={`hwm-${i}`} className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  High-water mark
                </Label>
                <Input
                  id={`hwm-${i}`}
                  value={c.high_water_mark ?? ""}
                  onChange={(e) =>
                    onChange?.(i, {
                      ...c,
                      high_water_mark: e.target.value === "" ? null : e.target.value,
                    })
                  }
                  placeholder="—"
                  className="h-7 font-mono text-xs"
                />
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => onReset?.(i)}
                aria-label={`Reset cursor for ${c.table}`}
              >
                <RotateCcw className="size-3.5" />
              </Button>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
