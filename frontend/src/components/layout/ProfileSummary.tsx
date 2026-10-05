import { getTranslations } from "next-intl/server";

import { Card } from "@/components/ui/Card";
import type { Profile } from "@/lib/api/types";

export async function ProfileSummary({ profile }: { profile: Profile }) {
  const t = await getTranslations("dashboard");
  const tRoles = await getTranslations("roles");
  const tStatus = await getTranslations("status");

  const rows = [
    { label: t("email"), value: profile.email ?? "—" },
    { label: t("role"), value: tRoles(profile.role) },
    { label: t("status"), value: tStatus(profile.status) },
  ];

  return (
    <Card>
      <h2 className="mb-4 font-semibold">{t("profileTitle")}</h2>
      <dl className="grid gap-3 sm:grid-cols-3">
        {rows.map((row) => (
          <div key={row.label}>
            <dt className="text-sm text-ink-muted">{row.label}</dt>
            <dd className="font-medium">{row.value}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}
