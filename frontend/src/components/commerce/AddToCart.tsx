"use client";

import { Minus, Plus, ShoppingCart } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button, buttonClasses } from "@/components/ui/Button";
import { Link } from "@/i18n/navigation";
import type { PublicProductDetail } from "@/lib/api/types";
import { addToCart, type CartLine, useCart } from "@/lib/cart";

export function AddToCart({ product }: { product: PublicProductDetail }) {
  const t = useTranslations("product");
  const tCart = useTranslations("cart");
  const [quantity, setQuantity] = useState(1);
  const [state, setState] = useState<"idle" | "added" | "conflict">("idle");
  const cart = useCart();

  if (!product.in_stock || product.max_quantity < 1) {
    return <p className="font-medium text-trust-caution">{t("outOfStock")}</p>;
  }

  const store = { id: product.store.id, slug: product.store.slug, name: product.store.name };
  const line: CartLine = {
    productId: product.id,
    quantity,
    name: product.name_i18n,
    priceLkr: product.price_lkr,
    imageUrl: product.images[0]?.url ?? null,
    maxQuantity: product.max_quantity,
  };

  function add(replace = false) {
    setState(addToCart(store, line, { replace }) === "added" ? "added" : "conflict");
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center rounded-lg border border-line" role="group" aria-label={t("quantity")}>
          <button
            type="button"
            aria-label={tCart("decrease")}
            disabled={quantity <= 1}
            onClick={() => setQuantity((q) => Math.max(1, q - 1))}
            className="p-2.5 disabled:opacity-40"
          >
            <Minus aria-hidden="true" className="h-4 w-4" />
          </button>
          <output aria-live="polite" className="w-8 text-center tabular-nums">
            {quantity}
          </output>
          <button
            type="button"
            aria-label={tCart("increase")}
            disabled={quantity >= product.max_quantity}
            onClick={() => setQuantity((q) => Math.min(product.max_quantity, q + 1))}
            className="p-2.5 disabled:opacity-40"
          >
            <Plus aria-hidden="true" className="h-4 w-4" />
          </button>
        </div>
        <Button onClick={() => add()}>
          <ShoppingCart aria-hidden="true" className="h-4 w-4" />
          {t("addToCart")}
        </Button>
      </div>

      {state === "added" ? (
        <Alert tone="success">
          {t("added")} ·{" "}
          <Link href="/cart" className="font-medium underline">
            {t("viewCart")}
          </Link>
        </Alert>
      ) : null}
      {state === "conflict" ? (
        <Alert title={t("replaceTitle")}>
          <p>{t("replaceBody", { store: cart?.store.name ?? "" })}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => add(true)}>
              {t("replaceConfirm")}
            </Button>
            <Link href="/cart" className={buttonClasses("ghost")}>
              {t("viewCart")}
            </Link>
          </div>
        </Alert>
      ) : null}
    </div>
  );
}
