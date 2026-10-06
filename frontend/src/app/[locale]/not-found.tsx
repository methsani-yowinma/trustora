import { useTranslations } from "next-intl";

import { buttonClasses } from "@/components/ui/Button";
import { Link } from "@/i18n/navigation";

export default function NotFound() {
  const t = useTranslations("errors");
  return (
    <div className="mx-auto max-w-lg space-y-3 py-24 text-center">
      <h1 className="text-2xl font-semibold">{t("notFoundTitle")}</h1>
      <p className="text-ink-muted">{t("notFoundBody")}</p>
      <Link href="/" className={buttonClasses("secondary")}>
        {t("backHome")}
      </Link>
    </div>
  );
}
