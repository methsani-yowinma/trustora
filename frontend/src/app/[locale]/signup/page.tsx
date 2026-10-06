import { getTranslations, setRequestLocale } from "next-intl/server";
import { Suspense } from "react";

import { AuthCard } from "@/components/auth/AuthCard";
import { SignupForm } from "@/components/auth/SignupForm";
import type { Locale } from "@/i18n/routing";

export default async function SignupPage({ params }: PageProps<"/[locale]/signup">) {
  const { locale } = await params;
  setRequestLocale(locale as Locale);
  const t = await getTranslations("auth");

  return (
    <AuthCard title={t("signupTitle")} subtitle={t("signupSubtitle")}>
      <Suspense>
        <SignupForm />
      </Suspense>
    </AuthCard>
  );
}
