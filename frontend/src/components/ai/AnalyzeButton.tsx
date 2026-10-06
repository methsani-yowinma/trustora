"use client";

import { Sparkles } from "lucide-react";
import { useTranslations } from "next-intl";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { clientApi } from "@/lib/api/browser";
import { useApiAction } from "@/lib/useApiAction";

/** Admin: ask Gemini to read a document. The result is analysis only; the admin still decides. */
export function AnalyzeButton({ evidenceId, again }: { evidenceId: string; again: boolean }) {
  const t = useTranslations("ai");
  const { run, pending, error } = useApiAction();
  return (
    <div className="space-y-2">
      <Button
        variant="secondary"
        disabled={pending}
        onClick={() => run(() => clientApi(`/admin/evidence/${evidenceId}/analyze`, { method: "POST" }))}
      >
        <Sparkles aria-hidden="true" className="h-4 w-4" />
        {pending ? t("analyzing") : again ? t("reanalyze") : t("analyze")}
      </Button>
      {error ? <Alert tone="error">{error}</Alert> : null}
    </div>
  );
}
