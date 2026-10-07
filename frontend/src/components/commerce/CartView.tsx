"use client";

import { Minus, Plus, Trash2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { SelectField } from "@/components/ui/Field";
import { RemoteImage } from "@/components/ui/RemoteImage";
import { Link } from "@/i18n/navigation";
import { removeFromCart, setQuantity, useCart } from "@/lib/cart";
import { DISTRICTS } from "@/lib/districts";
import { formatLkr, localize } from "@/lib/localize";

import { StoreTrustLine } from "./ProductCardView";
import { useQuote } from "./useQuote";

export function CartView({ signedIn }: { signedIn: boolean }) {
  const t = useTranslations("cart");
  const tDistricts = useTranslations("districts");
  const locale = useLocale();
  const cart = useCart();
  const [district, setDistrict] = useState<string>("COLOMBO");
  const { quote, error, loading } = useQuote(cart, district);

  if (!cart || cart.lines.length === 0) {
    return (
      <Card className="space-y-3 text-center">
        <p className="text-ink-muted">{t("empty")}</p>
        <Link href="/discover" className={buttonClasses("primary")}>
          {t("browse")}
        </Link>
      </Card>
    );
  }

  const issueFor = (productId: string) =>
    quote?.issues.find((i) => i.endsWith(`:${productId}`))?.split(":")[0] ?? null;

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
      <Card className="space-y-4">
        {quote ? <StoreTrustLine store={quote.store} /> : <p className="text-sm font-medium">{t("from", { store: cart.store.name })}</p>}
        <ul className="divide-y divide-line">
          {cart.lines.map((line) => {
            const priced = quote?.lines.find((l) => l.product_id === line.productId);
            const name = localize(priced?.name_i18n ?? line.name, locale);
            const issue = issueFor(line.productId);
            return (
              <li key={line.productId} className="flex gap-3 py-3">
                <RemoteImage src={priced?.image_url ?? line.imageUrl} alt={name?.text ?? ""} className="h-16 w-16 shrink-0 rounded-lg" />
                <div className="min-w-0 flex-1 space-y-1">
                  <Link href={`/products/${line.productId}`} lang={name?.lang} className="font-medium hover:underline">
                    {name?.text}
                  </Link>
                  <p className="text-sm text-ink-muted tabular-nums">
                    {formatLkr(priced?.unit_price_lkr ?? line.priceLkr, locale)}
                  </p>
                  {issue ? (
                    <p className="text-sm text-trust-risk">
                      {issue === "unavailable" ? t("unavailable") : t("insufficientStock")}
                    </p>
                  ) : null}
                </div>
                <div className="flex flex-col items-end gap-2">
                  <div className="flex items-center rounded-lg border border-line">
                    <button
                      type="button"
                      aria-label={t("decrease")}
                      onClick={() => setQuantity(line.productId, line.quantity - 1)}
                      className="p-1.5"
                    >
                      <Minus aria-hidden="true" className="h-4 w-4" />
                    </button>
                    <span className="w-7 text-center text-sm tabular-nums">{line.quantity}</span>
                    <button
                      type="button"
                      aria-label={t("increase")}
                      disabled={line.quantity >= line.maxQuantity}
                      onClick={() => setQuantity(line.productId, line.quantity + 1)}
                      className="p-1.5 disabled:opacity-40"
                    >
                      <Plus aria-hidden="true" className="h-4 w-4" />
                    </button>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeFromCart(line.productId)}
                    className="inline-flex items-center gap-1 text-xs text-ink-muted hover:text-trust-risk"
                  >
                    <Trash2 aria-hidden="true" className="h-3.5 w-3.5" />
                    {t("remove")}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      </Card>

      <Card className="h-fit space-y-4">
        <SelectField label={t("deliverTo")} name="district" value={district} onChange={(e) => setDistrict(e.target.value)}>
          {DISTRICTS.map((d) => (
            <option key={d} value={d}>
              {tDistricts(d)}
            </option>
          ))}
        </SelectField>
        {error ? <Alert tone="error">{error}</Alert> : null}
        {quote ? (
          <dl className="space-y-2 text-sm" aria-busy={loading}>
            <div className="flex justify-between">
              <dt>{t("subtotal")}</dt>
              <dd className="tabular-nums">{formatLkr(quote.subtotal_lkr, locale)}</dd>
            </div>
            <div className="flex justify-between">
              <dt>{t("delivery")}</dt>
              <dd className="tabular-nums">{formatLkr(quote.delivery.fee_lkr, locale)}</dd>
            </div>
            <p className="text-xs text-ink-muted">{t("deliveryEta", { days: quote.delivery.eta_days })}</p>
            <div className="flex justify-between border-t border-line pt-2 text-base font-semibold">
              <dt>{t("total")}</dt>
              <dd className="tabular-nums">{formatLkr(quote.total_lkr, locale)}</dd>
            </div>
          </dl>
        ) : (
          <p className="text-sm text-ink-muted">{t("checking")}</p>
        )}
        {quote && quote.issues.length > 0 ? <Alert tone="error">{t("fixIssues")}</Alert> : null}
        <Link
          href={signedIn ? { pathname: "/checkout", query: { district } } : { pathname: "/login", query: { next: `/${locale}/cart` } }}
          aria-disabled={!quote || quote.issues.length > 0}
          className={buttonClasses(
            "primary",
            `w-full ${!quote || quote.issues.length > 0 ? "pointer-events-none opacity-50" : ""}`,
          )}
        >
          {signedIn ? t("checkout") : t("signInToCheckout")}
        </Link>
        <p className="text-xs text-ink-muted">{t("pricesChecked")}</p>
      </Card>
    </div>
  );
}
