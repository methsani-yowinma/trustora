import { getTranslations } from "next-intl/server";

import { Alert } from "@/components/ui/Alert";
import { buttonClasses } from "@/components/ui/Button";
import { Link } from "@/i18n/navigation";
import type { UserRole } from "@/lib/api/types";

/** Shown when a page guard denies access or the API is unreachable. */
export async function AccessState({ kind, roles }: { kind: "forbidden" | "unavailable"; roles: UserRole[] }) {
  const t = await getTranslations("errors");
  const tRoles = await getTranslations("roles");

  return (
    <div className="mx-auto max-w-lg space-y-4 py-16">
      {kind === "forbidden" ? (
        <Alert tone="error" title={t("noAccessTitle")}>
          {t("noAccessBody", { roles: roles.map((role) => tRoles(role)).join(" / ") })}
        </Alert>
      ) : (
        <Alert tone="error" title={t("apiUnavailableTitle")}>
          {t("apiUnavailableBody")}
        </Alert>
      )}
      <Link href="/" className={buttonClasses("secondary")}>
        {t("backHome")}
      </Link>
    </div>
  );
}
