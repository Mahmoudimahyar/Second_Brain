"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { settingsApi } from "@/lib/api/client";

export default function FeedbackLoopSettings() {
  const [corpus, setCorpus] = useState("");
  const [template, setTemplate] = useState("extract_sentiment");

  const corpora = useQuery({
    queryKey: ["corpora"],
    queryFn: () => settingsApi.corpora(),
  });
  const policy = useQuery({
    queryKey: ["policy"],
    queryFn: () => settingsApi.policy(),
  });
  const block = useQuery({
    queryKey: ["feedback-loop", corpus, template],
    queryFn: () => settingsApi.feedbackLoop(corpus, template),
    enabled: !!corpus && !!template,
  });

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Feedback-loop policy</h1>
        <p className="text-sm text-gray-500">
          Active context block + blocklist per (corpus, template). K=4 cap
          per ADR-018.
        </p>
      </header>

      {policy.data && (
        <section className="rounded border p-3 text-sm">
          <strong>Caps:</strong> K={policy.data.caps.positive_examples_k} ·
          Blocklist max={policy.data.caps.blocklist_max}
        </section>
      )}

      <section className="space-y-2">
        <label className="block text-sm">
          Corpus:
          <select
            className="ml-2 rounded border px-2 py-1"
            value={corpus}
            onChange={(e) => setCorpus(e.target.value)}
          >
            <option value="">— pick one —</option>
            {corpora.data?.corpora.map((c) => (
              <option key={c.corpus_id} value={c.corpus_id}>
                {c.corpus_id} ({c.decision_count})
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          Template:
          <input
            className="ml-2 rounded border px-2 py-1"
            value={template}
            onChange={(e) => setTemplate(e.target.value)}
          />
        </label>
      </section>

      {block.data && (
        <section className="space-y-3">
          <div className="text-xs text-gray-500">
            context_hash: <code>{block.data.context_hash}</code> ·{" "}
            {block.data.feedback_log_count} total decisions
          </div>
          <div>
            <h2 className="font-semibold">Examples ({block.data.examples.length})</h2>
            <ul className="list-disc pl-5 text-sm">
              {block.data.examples.map((e, i) => (
                <li key={i}>
                  {e.pattern}{" "}
                  <span className="text-xs text-gray-500">
                    (score {e.selection_score.toFixed(3)})
                  </span>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h2 className="font-semibold">Blocklist ({block.data.blocklist.length})</h2>
            <ul className="list-disc pl-5 text-sm">
              {block.data.blocklist.map((b, i) => (
                <li key={i}>
                  {b.pattern}{" "}
                  <span className="text-xs text-gray-500">
                    (hits {b.hit_count})
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}
    </div>
  );
}
