"use client";

import * as React from "react";
import { DayPicker } from "react-day-picker";
import "react-day-picker/style.css";

import { cn } from "@/lib/utils";

export type CalendarProps = React.ComponentProps<typeof DayPicker>;

/**
 * Calendar — thin wrapper over react-day-picker v10 with Aurora
 * background + border. v10 changed the classNames API significantly
 * vs v8; the deeper restyle (per-day classes, custom nav icons) is a
 * V1.6 polish — out-of-the-box dark/light theming works against our
 * tokens since react-day-picker inherits text colors.
 */
function Calendar({ className, ...props }: CalendarProps) {
  return (
    <div
      className={cn(
        "rounded-md border border-border bg-surface-elevated p-2 text-foreground",
        className,
      )}
    >
      <DayPicker {...props} />
    </div>
  );
}
Calendar.displayName = "Calendar";

export { Calendar };
