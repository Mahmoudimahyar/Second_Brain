import Link from "next/link";

export default function TeamsPicker() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Per-team dashboards</h1>
      <p className="text-sm text-gray-500">Ships in V1.5c.</p>
      <ul className="grid grid-cols-3 gap-3">
        {[
          { href: "/teams/pm", title: "PM" },
          { href: "/teams/social", title: "Social" },
          { href: "/teams/marketing", title: "Marketing" },
        ].map((c) => (
          <li key={c.href}>
            <Link href={c.href} className="block rounded border p-4 hover:bg-gray-50">
              {c.title}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
