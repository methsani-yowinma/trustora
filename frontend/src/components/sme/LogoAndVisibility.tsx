"use client";

import { Eye, EyeOff } from "lucide-react";
import { useTranslations } from "next-intl";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { FileUploadButton, IMAGE_ACCEPT } from "@/components/ui/FileUploadButton";
import { RemoteImage } from "@/components/ui/RemoteImage";
import { clientApi } from "@/lib/api/browser";
import type { Sme } from "@/lib/api/types";
import { useApiAction } from "@/lib/useApiAction";

export function LogoUploader({ sme }: { sme: Sme }) {
  const t = useTranslations("sme.store");
  const tCommon = useTranslations("common");
  const { run, pending, error } = useApiAction();

  function upload(file: File) {
    const body = new FormData();
    body.append("file", file);
    void run(() => clientApi<Sme>("/smes/me/logo", { method: "POST", body }));
  }

  return (
    <Card className="space-y-4">
      <h2 className="font-semibold">{t("logo")}</h2>
      <div className="flex flex-wrap items-center gap-4">
        <RemoteImage src={sme.logo_url} alt={sme.name} className="h-20 w-20 rounded-xl border border-line" />
        <div className="space-y-2">
          <FileUploadButton
            label={pending ? tCommon("uploading") : t("uploadLogo")}
            accept={IMAGE_ACCEPT}
            disabled={pending}
            onSelect={upload}
          />
          <p className="text-sm text-ink-muted">{t("logoHint")}</p>
        </div>
      </div>
      {error ? <Alert tone="error">{error}</Alert> : null}
    </Card>
  );
}

export function PublishToggle({ sme }: { sme: Sme }) {
  const t = useTranslations("sme.store");
  const { run, pending, error } = useApiAction();
  const Icon = sme.is_published ? Eye : EyeOff;

  return (
    <Card className="space-y-4">
      <h2 className="font-semibold">{t("visibility")}</h2>
      <p className="flex items-center gap-2 text-sm">
        <Icon aria-hidden="true" className="h-4 w-4 text-ink-muted" />
        {sme.is_published ? t("published") : t("unpublished")}
      </p>
      {error ? <Alert tone="error">{error}</Alert> : null}
      <Button
        variant={sme.is_published ? "secondary" : "primary"}
        disabled={pending}
        onClick={() =>
          run(() => clientApi<Sme>("/smes/me", { method: "PATCH", body: { is_published: !sme.is_published } }))
        }
      >
        {sme.is_published ? t("unpublish") : t("publish")}
      </Button>
    </Card>
  );
}
