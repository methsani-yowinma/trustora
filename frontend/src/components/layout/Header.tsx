import { Package, Search } from "lucide-react";
import { getTranslations } from "next-intl/server";

import { SignOutButton } from "@/components/auth/SignOutButton";
import { CartButton } from "@/components/commerce/CartButton";
import { buttonClasses } from "@/components/ui/Button";
import { Logo } from "@/components/ui/Logo";
import { Link } from "@/i18n/navigation";
import { getSession } from "@/lib/auth";

import { LanguageSwitcher } from "./LanguageSwitcher";

export async function Header() {
  const t = await getTranslations("nav");
  const tRoles = await getTranslations("roles");
  const session = await getSession();
  const profile = session.status === "authenticated" ? session.profile : null;

  return (
    <header className="border-b border-line bg-surface/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3 sm:px-6">
        <Link href="/" aria-label={t("home")}>
          <Logo />
        </Link>

        <nav aria-label={t("mainNavigation")} className="flex flex-wrap items-center justify-end gap-1 sm:gap-2">
          {/* On small screens these collapse to icons so the header stays on one row. */}
          <Link href="/discover" aria-label={t("discover")} className={buttonClasses("ghost", "px-2.5 sm:px-3")}>
            <Search aria-hidden="true" className="h-5 w-5 sm:hidden" />
            <span className="hidden sm:inline">{t("discover")}</span>
          </Link>
          {profile?.role === "CUSTOMER" ? (
            <Link href="/orders" aria-label={t("orders")} className={buttonClasses("ghost", "px-2.5 md:px-3")}>
              <Package aria-hidden="true" className="h-5 w-5 md:hidden" />
              <span className="hidden md:inline">{t("orders")}</span>
            </Link>
          ) : null}
          {!profile || profile.role === "CUSTOMER" ? <CartButton /> : null}
          {profile?.role === "SME" ? (
            <Link href="/sme" className={buttonClasses("ghost", "px-3")}>
              {t("smeDashboard")}
            </Link>
          ) : null}
          {profile?.role === "ADMIN" ? (
            <Link href="/admin" className={buttonClasses("ghost", "px-3")}>
              {t("admin")}
            </Link>
          ) : null}

          <LanguageSwitcher />

          {profile ? (
            <>
              <span className="hidden text-sm text-ink-muted md:inline">
                {t("signedInAs", { name: profile.full_name ?? profile.email ?? tRoles(profile.role) })}
              </span>
              <SignOutButton />
            </>
          ) : (
            <>
              <Link href="/login" className={buttonClasses("ghost", "px-3")}>
                {t("login")}
              </Link>
              {/* On small screens the login page links to signup; keeps the header on one row. */}
              <span className="hidden sm:inline-flex">
                <Link href="/signup" className={buttonClasses("primary", "px-3 py-2")}>
                  {t("signup")}
                </Link>
              </span>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
