"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchRiskReport, type RiskReport } from "@/lib/risk-report";

export function RiskReportCard({ userId }: { userId: string }) {
  const { data, isLoading } = useQuery<RiskReport>({
    queryKey: ["risk-report", userId],
    queryFn: () => fetchRiskReport(userId),
  });

  if (isLoading) return null;
  if (!data) return null;

  const danger = data.count > 0;

  return (
    <div
      className={`mt-10 rounded-lg border p-5 ${
        danger
          ? "border-red-300 bg-red-50/60"
          : "border-emerald-300 bg-emerald-50/60"
      }`}
    >
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">
          Offboarding risk report
        </h2>
        <span
          className={`rounded-full px-3 py-1 text-xs font-medium ${
            danger
              ? "bg-red-200 text-red-900"
              : "bg-emerald-200 text-emerald-900"
          }`}
        >
          {danger ? `${data.count} secret${data.count === 1 ? "" : "s"} need rotation` : "All clear"}
        </span>
      </div>

      <p className="mt-2 text-sm text-muted-foreground">
        Secrets this user has revealed and that have NOT been rotated since. Rotate these
        before disabling the user — otherwise they retain access to credentials they once viewed.
      </p>

      {danger ? (
        <div className="mt-4 overflow-hidden rounded-md border border-red-200 bg-card">
          <table className="w-full text-sm">
            <thead className="border-b border-red-200 bg-red-100/60">
              <tr className="text-left">
                <th className="px-3 py-2 font-medium">Device</th>
                <th className="px-3 py-2 font-medium">Kind</th>
                <th className="px-3 py-2 font-medium">Secret</th>
                <th className="px-3 py-2 font-medium">Last seen</th>
                <th className="px-3 py-2 font-medium">Last rotated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-red-100">
              {data.items.map((item) => (
                <tr
                  key={`${item.device_id}-${item.secret_kind}-${item.secret_identifier}`}
                >
                  <td className="px-3 py-2 font-medium">{item.device_name}</td>
                  <td className="px-3 py-2 font-mono text-xs">{item.secret_kind}</td>
                  <td className="px-3 py-2 font-mono text-xs">
                    {item.secret_label ?? item.secret_identifier}
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">
                    {new Date(item.revealed_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">
                    {item.last_rotated_at
                      ? new Date(item.last_rotated_at).toLocaleString()
                      : "never"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="mt-3 text-sm text-emerald-900">
          This user has not revealed any secrets, or every secret they revealed has since been rotated.
        </p>
      )}
    </div>
  );
}
