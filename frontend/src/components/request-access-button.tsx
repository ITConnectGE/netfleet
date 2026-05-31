"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useToast } from "@/components/toast";
import { createAccessRequest } from "@/lib/access-requests";

interface Props {
  scopeType: "tenant" | "site" | "device";
  scopeId: string;
  scopeLabel: string;
  variant?: "inline" | "block";
}

export function RequestAccessButton({
  scopeType,
  scopeId,
  scopeLabel,
  variant = "inline",
}: Props) {
  const qc = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");

  const m = useMutation({
    mutationFn: () =>
      createAccessRequest({
        scope_type: scopeType,
        scope_id: scopeId,
        reason: reason.trim() || null,
      }),
    onSuccess: () => {
      setOpen(false);
      setReason("");
      qc.invalidateQueries({ queryKey: ["access-requests"] });
      qc.invalidateQueries({ queryKey: ["notifications"] });
      toast.success("Request sent", `Admins will see "${scopeLabel}" in their inbox`);
    },
    onError: (e: Error) => toast.error("Request failed", e.message),
  });

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={
          variant === "inline"
            ? "text-xs text-primary hover:underline"
            : "rounded-md border border-primary/40 bg-primary/5 px-3 py-1.5 text-sm font-medium text-primary hover:bg-primary/10"
        }
      >
        Request access
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-xl">
            <h3 className="text-lg font-semibold">
              Request access to {scopeType}
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Asking for <span className="font-mono">{scopeLabel}</span>.
              An admin will see this in the dashboard and by email, then choose
              which role(s) to grant.
            </p>
            <label className="mt-4 block space-y-1 text-sm font-medium">
              Reason (optional)
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={4}
                maxLength={2048}
                className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                placeholder="e.g. need to investigate a firewall rule for ticket #123"
              />
              <p className="text-[11px] italic text-muted-foreground">
                The admin reads this when deciding — be specific.
              </p>
            </label>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => m.mutate()}
                disabled={m.isPending}
                className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
              >
                {m.isPending ? "Sending…" : "Send request"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
