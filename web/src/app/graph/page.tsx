import Link from "next/link";

export default function GraphPicker() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Graph viewer</h1>
      <p className="text-sm text-gray-500">
        Three independent views per ADR-012.
      </p>
      <ul className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        {[
          { href: "/graph/structural", level: "A", title: "Structural", desc: "Pass-1 forum mechanics (deterministic)" },
          { href: "/graph/clusters", level: "B", title: "Clusters", desc: "Topic + Cluster aggregates" },
          { href: "/graph/analyzed", level: "C", title: "Analyzed", desc: "Full graph incl. Pass-4 + cross-graph" },
        ].map((card) => (
          <li key={card.href}>
            <Link href={card.href} className="block rounded border p-4 hover:bg-gray-50">
              <div className="text-xs text-gray-400">Level {card.level}</div>
              <div className="font-semibold">{card.title}</div>
              <div className="text-xs text-gray-500 mt-1">{card.desc}</div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
