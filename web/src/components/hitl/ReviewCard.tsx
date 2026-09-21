"use client";

import { type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export interface ReviewCardProps {
  itemId: string;
  itemType: string;
  status: string;
  claimedBy?: string | null;
  children: ReactNode;
}

export function ReviewCard({
  itemId,
  itemType,
  status,
  claimedBy,
  children,
}: ReviewCardProps) {
  const variant: "secondary" | "warning" | "success" | "default" =
    status === "pending"
      ? "secondary"
      : status === "escalated"
        ? "warning"
        : status === "resolved"
          ? "success"
          : "default";
  return (
    <Card>
      <CardHeader className="flex items-center justify-between gap-2">
        <div>
          <CardTitle className="font-mono text-xs">{itemId}</CardTitle>
          <p className="text-xs text-gray-500">{itemType}</p>
        </div>
        <div className="flex gap-2 items-center">
          {claimedBy && (
            <Badge variant="default">claimed: {claimedBy}</Badge>
          )}
          <Badge variant={variant}>{status}</Badge>
        </div>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}
