"use client";
import { useQuery } from "@tanstack/react-query";
import { settingsApi } from "@/lib/api/client";

export default function CorporaSettings() {
  const { data, isLoading } = useQuery({
    queryKey: ["corpora"],
    queryFn: () => settingsApi.corpora(),
  });
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Corpora</h1>
      {isLoading && <p>Loading…</p>}
      {data && (
        <ul className="space-y-2">
          {data.corpora.map((c) => (
            <li key={c.corpus_id} className="rounded border p-3">
              <div className="font-medium">{c.corpus_id}</div>
              <div className="text-xs text-gray-500">
                {c.decision_count} HITL decisions
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
