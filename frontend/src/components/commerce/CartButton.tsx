"use client";

import { ShoppingCart } from "lucide-react";
import { useTranslations } from "next-intl";

import { buttonClasses } from "@/components/ui/Button";
import { Link } from "@/i18n/navigation";
import { cartCount, useCart } from "@/lib/cart";

export function CartButton() {
  const t = useTranslations("nav");
  const count = cartCount(useCart());
  return (
    <Link href="/cart" aria-label={t("cartCount", { count })} className={buttonClasses("ghost", "relative px-2.5")}>
      <ShoppingCart aria-hidden="true" className="h-5 w-5" />
      {count > 0 ? (
        <span
          aria-hidden="true"
          className="absolute -top-0.5 -right-0.5 min-w-5 rounded-full bg-brand-600 px-1 text-center text-xs leading-5 font-semibold text-white"
        >
          {count}
        </span>
      ) : null}
    </Link>
  );
}
