import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export interface LoadingStateProps {
  variant?: "card-list" | "table" | "graph" | "dashboard";
  rows?: number;
  cols?: number;
  className?: string;
}

export function LoadingState({
  variant = "card-list",
  rows = 5,
  cols = 4,
  className,
}: LoadingStateProps) {
  if (variant === "table") {
    return (
      <div className={cn("space-y-2", className)} aria-busy="true">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="flex items-center gap-3">
            {Array.from({ length: cols }).map((__, j) => (
              <Skeleton key={j} className="h-4 flex-1" />
            ))}
          </div>
        ))}
      </div>
    );
  }

  if (variant === "graph") {
    return (
      <div
        className={cn("relative h-[500px] rounded-lg border border-border bg-surface/40", className)}
        aria-busy="true"
      >
        <Skeleton className="h-full w-full rounded-lg" />
      </div>
    );
  }

  if (variant === "dashboard") {
    return (
      <div className={cn("grid grid-cols-1 gap-4 md:grid-cols-3", className)} aria-busy="true">
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} className="h-32 rounded-lg" />
        ))}
        <Skeleton className="col-span-full h-64 rounded-lg" />
      </div>
    );
  }

  // card-list
  return (
    <div className={cn("space-y-3", className)} aria-busy="true">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="rounded-lg border border-border p-4">
          <Skeleton className="mb-2 h-4 w-1/2" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="mt-1 h-3 w-3/4" />
        </div>
      ))}
    </div>
  );
}
