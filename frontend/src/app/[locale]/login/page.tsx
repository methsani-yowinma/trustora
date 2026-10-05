import { getTranslations, setRequestLocale } from "next-intl/server";
import { Suspense } from "react";

import { AuthCard } from "@/components/auth/AuthCard";
import { LoginForm } from "@/components/auth/LoginForm";
import type { Locale } from "@/i18n/routing";

export default async function LoginPage({ params }: PageProps<"/[locale]/login">) {
  const { locale } = await params;
  setRequestLocale(locale as Locale);
  const t = await getTranslations("auth");

  return (
    <AuthCard title={t("loginTitle")} subtitle={t("loginSubtitle")}>
      <Suspense>
        <LoginForm />
      </Suspense>
    </AuthCard>
  );
}
