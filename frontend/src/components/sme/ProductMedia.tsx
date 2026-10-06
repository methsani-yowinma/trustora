"use client";

import { Trash2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { type FormEvent, useRef } from "react";

import { EvidenceList } from "@/components/trust/EvidenceList";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, SelectField } from "@/components/ui/Field";
import { DOCUMENT_ACCEPT, FileUploadButton, IMAGE_ACCEPT } from "@/components/ui/FileUploadButton";
import { RemoteImage } from "@/components/ui/RemoteImage";
import { useRouter } from "@/i18n/navigation";
import { clientApi } from "@/lib/api/browser";
import type { ProductDetail } from "@/lib/api/types";
import { localizedString } from "@/lib/localize";
import { useApiAction } from "@/lib/useApiAction";

export function ProductImages({ product }: { product: ProductDetail }) {
  const t = useTranslations("sme.products");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const { run, pending, error } = useApiAction();
  const name = localizedString(product.name_i18n, locale);

  function upload(file: File) {
    const body = new FormData();
    body.append("file", file);
    void run(() => clientApi(`/sme/products/${product.id}/images`, { method: "POST", body }));
  }

  return (
    <Card className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h2 className="font-semibold">{t("images")}</h2>
          <p className="text-sm text-ink-muted">{t("imagesHint")}</p>
        </div>
        <FileUploadButton
          label={pending ? tCommon("uploading") : t("addImage")}
          accept={IMAGE_ACCEPT}
          disabled={pending || product.images.length >= 8}
          onSelect={upload}
        />
      </div>
      {product.images.length === 0 ? (
        <p className="text-sm text-ink-muted">{t("noImages")}</p>
      ) : (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {product.images.map((image, index) => (
            <li key={image.id} className="group relative">
              <RemoteImage
                src={image.url}
                alt={`${name} ${index + 1}`}
                className="aspect-square w-full rounded-lg border border-line"
              />
              <button
                type="button"
                disabled={pending}
                onClick={() =>
                  run(() => clientApi(`/sme/products/${product.id}/images/${image.id}`, { method: "DELETE" }))
                }
                aria-label={`${tCommon("remove")} ${name} ${index + 1}`}
                className="absolute top-2 right-2 rounded-md bg-surface/90 p-1.5 text-trust-risk shadow"
              >
                <Trash2 aria-hidden="true" className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
      {error ? <Alert tone="error">{error}</Alert> : null}
    </Card>
  );
}

export function ProductEvidence({ product }: { product: ProductDetail }) {
  const t = useTranslations("sme.products");
  const { run, pending, error } = useApiAction();
  const formRef = useRef<HTMLFormElement>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const body = new FormData(event.currentTarget);
    const result = await run(() => clientApi(`/sme/products/${product.id}/evidence`, { method: "POST", body }));
    if (result) formRef.current?.reset();
  }

  return (
    <Card className="space-y-4">
      <div className="space-y-1">
        <h2 className="font-semibold">{t("evidenceTitle")}</h2>
        <p className="text-sm text-ink-muted">{t("evidenceBody")}</p>
      </div>
      <EvidenceList items={product.evidence} emptyText={t("noEvidence")} />
      <form ref={formRef} onSubmit={onSubmit} className="grid gap-3 lg:grid-cols-[14rem_1fr]">
        <SelectField label={t("evidenceType")} name="evidence_type" defaultValue="PRODUCT_DOCUMENT">
          <option value="PRODUCT_DOCUMENT">{t("evidenceTypePRODUCT_DOCUMENT")}</option>
          <option value="PRODUCT_IMAGE">{t("evidenceTypePRODUCT_IMAGE")}</option>
        </SelectField>
        <Field label={t("evidenceDescription")} name="description" required minLength={3} maxLength={500} />
        <Field
          label={t("uploadEvidence")}
          name="file"
          type="file"
          accept={DOCUMENT_ACCEPT}
          required
          className="lg:col-span-2"
        />
        <div className="lg:col-span-2">
          <Button type="submit" disabled={pending}>
            {t("uploadEvidence")}
          </Button>
        </div>
      </form>
      {error ? <Alert tone="error">{error}</Alert> : null}
    </Card>
  );
}

export function RemoveProductButton({ productId }: { productId: string }) {
  const t = useTranslations("sme.products");
  const tCommon = useTranslations("common");
  const router = useRouter();
  const { run, pending, error } = useApiAction();

  async function remove() {
    if (!window.confirm(tCommon("confirmRemove"))) return;
    const done = await run(
      async () => {
        await clientApi(`/sme/products/${productId}`, { method: "DELETE" });
        return true;
      },
      { refresh: false },
    );
    if (done) router.push("/sme/products");
  }

  return (
    <div className="space-y-2">
      <Button variant="secondary" onClick={remove} disabled={pending} className="text-trust-risk">
        <Trash2 aria-hidden="true" className="h-4 w-4" />
        {t("removeProduct")}
      </Button>
      {error ? <Alert tone="error">{error}</Alert> : null}
    </div>
  );
}
