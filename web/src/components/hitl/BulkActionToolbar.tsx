"use client";

import { Button } from "@/components/ui/button";

export interface BulkActionToolbarProps {
  selectedCount: number;
  onBulkAccept: () => void;
  onBulkReject: () => void;
  onClearSelection: () => void;
  disabled?: boolean;
}

export function BulkActionToolbar({
  selectedCount,
  onBulkAccept,
  onBulkReject,
  onClearSelection,
  disabled,
}: BulkActionToolbarProps) {
  if (selectedCount === 0) return null;
  return (
    <div
      role="toolbar"
      aria-label="Bulk actions"
      className="sticky bottom-0 z-10 flex gap-2 items-center bg-gray-900 text-white px-4 py-2 rounded shadow-lg"
    >
      <span className="text-sm">{selectedCount} selected</span>
      <span className="flex-1" />
      <Button
        size="sm"
        variant="default"
        onClick={onBulkAccept}
        disabled={disabled}
      >
        Bulk accept
      </Button>
      <Button
        size="sm"
        variant="destructive"
        onClick={onBulkReject}
        disabled={disabled}
      >
        Bulk reject
      </Button>
      <Button
        size="sm"
        variant="ghost"
        className="text-white hover:bg-gray-800"
        onClick={onClearSelection}
      >
        Clear
      </Button>
    </div>
  );
}
