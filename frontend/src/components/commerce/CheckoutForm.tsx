"use client";

import { Banknote, CreditCard } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { type FormEvent, useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, SelectField } from "@/components/ui/Field";
import { Link, useRouter } from "@/i18n/navigation";
import { ApiError } from "@/lib/api/client";
import { clientApi } from "@/lib/api/browser";
import type { Order } from "@/lib/api/types";
import { clearCart, useCart } from "@/lib/cart";
import { cn } from "@/lib/cn";
import { DISTRICTS } from "@/lib/districts";
import { formatLkr, localizedString } from "@/lib/localize";

import { useQuote } from "./useQuote";

export function CheckoutForm({ initialDistrict, defaultName }: { initialDistrict: string; defaultName: string }) {
  const t = useTranslations("checkout");
  const tCart = useTranslations("cart");
  const tProduct = useTranslations("product");
  const tDistricts = useTranslations("districts");
  const tErrors = useTranslations("apiErrors");
  const locale = useLocale();
  const router = useRouter();
  const cart = useCart();
  const [district, setDistrict] = useState(initialDistrict);
  const [method, setMethod] = useState<"COD" | "MOCK_CARD">("COD");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  // One key per checkout attempt: a retried or double-clicked submit cannot create two orders.
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const { quote, error: quoteError, refresh } = useQuote(cart, district);

  if (!cart || cart.lines.length === 0) {
    return <Alert>{t("emptyCart")}</Alert>;
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!quote || !cart) return;
    const form = new FormData(event.currentTarget);
    const optional = (key: string) => String(form.get(key) ?? "").trim() || undefined;
    setPending(true);
    setError(null);
    try {
      const order = await clientApi<Order>("/checkout", {
        method: "POST",
        body: {
          items: cart.lines.map((l) => ({ product_id: l.productId, quantity: l.quantity })),
          shipping_address: {
            recipient_name: String(form.get("recipient_name") ?? "").trim(),
            phone: String(form.get("phone") ?? "").trim(),
            address_line1: String(form.get("address_line1") ?? "").trim(),
            address_line2: optional("address_line2"),
            city: String(form.get("city") ?? "").trim(),
            district,
            postal_code: optional("postal_code"),
          },
          payment_method: method,
          idempotency_key: idempotencyKey,
          expected_total_lkr: quote.total_lkr,
        },
      });
      clearCart();
      router.push(`/orders/${order.id}`);
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "generic";
      if (code === "price_changed" || code === "cart_changed") {
        setError(t("priceChanged"));
        refresh();
      } else {
        const key = code as Parameters<typeof tErrors>[0];
        setError(tErrors.has(key) ? tErrors(key) : tErrors("generic"));
      }
      setPending(false);
    }
  }

  const methods = [
    { value: "COD" as const, label: t("cod"), hint: t("codHint"), Icon: Banknote },
    { value: "MOCK_CARD" as const, label: t("mockCard"), hint: t("mockCardHint"), Icon: CreditCard },
  ];

  return (
    <form onSubmit={onSubmit} className="grid gap-6 lg:grid-cols-[1fr_22rem]">
      <div className="space-y-6">
        <Card className="space-y-4">
          <h2 className="font-semibold">{t("address")}</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("recipient")} name="recipient_name" required maxLength={120} defaultValue={defaultName} autoComplete="name" />
            <Field label={t("phone")} name="phone" type="tel" required pattern="\+?[0-9 ]{7,20}" autoComplete="tel" placeholder="+94 77 123 4567" />
            <Field label={t("line1")} name="address_line1" required minLength={3} maxLength={200} autoComplete="address-line1" className="sm:col-span-2" />
            <Field label={t("line2")} name="address_line2" maxLength={200} autoComplete="address-line2" className="sm:col-span-2" />
            <Field label={t("city")} name="city" required maxLength={120} autoComplete="address-level2" />
            <SelectField label={t("district")} name="district" value={district} onChange={(e) => setDistrict(e.target.value)}>
              {DISTRICTS.map((d) => (
                <option key={d} value={d}>
                  {tDistricts(d)}
                </option>
              ))}
            </SelectField>
            <Field label={t("postalCode")} name="postal_code" inputMode="numeric" pattern="[0-9]{5}" autoComplete="postal-code" />
          </div>
        </Card>

        <Card className="space-y-3">
          <fieldset className="space-y-2">
            <legend className="mb-2 font-semibold">{t("payment")}</legend>
            {methods.map(({ value, label, hint, Icon }) => (
              <label
                key={value}
                className={cn(
                  "flex cursor-pointer gap-3 rounded-lg border p-3 text-sm has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-brand-600",
                  method === value ? "border-brand-600 bg-brand-50" : "border-line",
                )}
              >
                <input type="radio" name="payment_method" value={value} checked={method === value} onChange={() => setMethod(value)} className="sr-only" />
                <Icon aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />
                <span>
                  <span className="block font-medium">{label}</span>
                  <span className="text-ink-muted">{hint}</span>
                </span>
              </label>
            ))}
          </fieldset>
        </Card>
      </div>

      <Card className="h-fit space-y-4">
        <h2 className="font-semibold">{t("summary")}</h2>
        {quote ? (
          <>
            <p className="text-xs text-ink-muted">
              {t("trustReminder", { store: quote.store.name })}{" "}
              <Link href={`/stores/${quote.store.slug}/passport`} className="text-brand-700 underline">
                {tProduct("viewPassport")}
              </Link>
            </p>
            <ul className="space-y-1 text-sm">
              {quote.lines.map((line) => (
                <li key={line.product_id} className="flex justify-between gap-3">
                  <span>
                    {localizedString(line.name_i18n, locale)} × {line.quantity}
                  </span>
                  <span className="tabular-nums">{formatLkr(line.line_total_lkr, locale)}</span>
                </li>
              ))}
            </ul>
            <dl className="space-y-1 border-t border-line pt-2 text-sm">
              <div className="flex justify-between">
                <dt>{tCart("delivery")}</dt>
                <dd className="tabular-nums">{formatLkr(quote.delivery.fee_lkr, locale)}</dd>
              </div>
              <div className="flex justify-between text-base font-semibold">
                <dt>{tCart("total")}</dt>
                <dd className="tabular-nums">{formatLkr(quote.total_lkr, locale)}</dd>
              </div>
            </dl>
          </>
        ) : (
          <p className="text-sm text-ink-muted">{tCart("checking")}</p>
        )}
        {quoteError ? <Alert tone="error">{quoteError}</Alert> : null}
        {quote && quote.issues.length > 0 ? <Alert tone="error">{tCart("fixIssues")}</Alert> : null}
        {error ? <Alert tone="error">{error}</Alert> : null}
        <Button type="submit" className="w-full" disabled={pending || !quote || quote.issues.length > 0}>
          {pending ? t("placing") : t("placeOrder")}
        </Button>
      </Card>
    </form>
  );
}
