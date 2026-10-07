"use client";

import { useLocale, useTranslations } from "next-intl";
import { type FormEvent, useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, SelectField } from "@/components/ui/Field";
import { LocalizedFields, readLocalized } from "@/components/ui/LocalizedFields";
import { useRouter } from "@/i18n/navigation";
import { clientApi } from "@/lib/api/browser";
import type { Category, ProductDetail } from "@/lib/api/types";
import { localizedString } from "@/lib/localize";
import { useApiAction } from "@/lib/useApiAction";

/** Create (no `product`) or edit a product's details. */
export function ProductForm({ categories, product }: { categories: Category[]; product?: ProductDetail }) {
  const t = useTranslations("sme.products");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const router = useRouter();
  const { run, pending, error } = useApiAction();
  const [saved, setSaved] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaved(false);
    const form = new FormData(event.currentTarget);
    const body = {
      category_id: Number(form.get("category_id")),
      name_i18n: readLocalized(form, "name") ?? {},
      description_i18n: readLocalized(form, "description"),
      price_lkr: String(form.get("price_lkr") ?? ""),
      stock: Number(form.get("stock") ?? 0),
      status: form.get("status"),
    };

    if (product) {
      const result = await run(() =>
        clientApi<ProductDetail>(`/sme/products/${product.id}`, { method: "PATCH", body }),
      );
      if (result) setSaved(true);
      return;
    }
    const created = await run(() => clientApi<ProductDetail>("/sme/products", { method: "POST", body }), {
      refresh: false,
    });
    if (created) router.push(`/sme/products/${created.id}`);
  }

  return (
    <Card>
      <form onSubmit={onSubmit} className="space-y-5">
        <LocalizedFields name="name" label={t("name")} maxLength={160} required defaultValue={product?.name_i18n} />
        <LocalizedFields
          name="description"
          label={t("description")}
          multiline
          maxLength={5000}
          defaultValue={product?.description_i18n}
        />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <SelectField label={t("category")} name="category_id" required defaultValue={product?.category_id ?? ""}>
            <option value="" disabled>
              {t("chooseCategory")}
            </option>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {localizedString(category.name_i18n, locale)}
              </option>
            ))}
          </SelectField>
          <Field
            label={t("price")}
            name="price_lkr"
            type="number"
            inputMode="decimal"
            min="0.01"
            max="10000000"
            step="0.01"
            required
            defaultValue={product?.price_lkr}
          />
          <Field
            label={t("stock")}
            name="stock"
            type="number"
            inputMode="numeric"
            min="0"
            max="1000000"
            step="1"
            required
            defaultValue={product?.stock ?? 0}
          />
          <SelectField label={t("status")} name="status" defaultValue={product?.status ?? "ACTIVE"}>
            <option value="ACTIVE">{t("statusACTIVE")}</option>
            <option value="HIDDEN">{t("statusHIDDEN")}</option>
          </SelectField>
        </div>
        {error ? <Alert tone="error">{error}</Alert> : null}
        {saved ? <Alert tone="success">{tCommon("saved")}</Alert> : null}
        <Button type="submit" disabled={pending}>
          {pending ? tCommon("saving") : product ? tCommon("save") : t("create")}
        </Button>
      </form>
    </Card>
  );
}
