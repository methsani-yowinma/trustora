"use client";

import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { type FormEvent, useState } from "react";
import { z } from "zod";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Link, useRouter } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";
import { apiFetch } from "@/lib/api/client";
import type { Profile, UserRole } from "@/lib/api/types";
import { safeNextPath } from "@/lib/redirect";
import { createClient } from "@/lib/supabase/client";

import { type AuthErrorKey, authErrorKey } from "./authErrors";

const schema = z.object({
  email: z.email(),
  password: z.string().min(1),
});

const HOME_BY_ROLE: Record<UserRole, string> = { CUSTOMER: "/", SME: "/sme", ADMIN: "/admin" };

/** `next` values carry a locale prefix (e.g. /si/sme); the locale-aware router adds its own. */
function stripLocale(path: string): string {
  for (const locale of routing.locales) {
    if (path === `/${locale}`) return "/";
    if (path.startsWith(`/${locale}/`)) return path.slice(locale.length + 1);
  }
  return path;
}

export function LoginForm() {
  const t = useTranslations("auth");
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<AuthErrorKey | "callbackFailed" | null>(
    searchParams.get("error") === "callback" ? "callbackFailed" : null,
  );
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setFieldError(null);

    const form = new FormData(event.currentTarget);
    const parsed = schema.safeParse({ email: form.get("email"), password: form.get("password") });
    if (!parsed.success) {
      setFieldError(t("errors.invalidEmail"));
      return;
    }

    setPending(true);
    const { data, error: signInError } = await createClient().auth.signInWithPassword(parsed.data);
    if (signInError || !data.session) {
      setError(signInError ? authErrorKey(signInError) : "generic");
      setPending(false);
      return;
    }

    // Route by role as reported by the API, which is the source of truth for roles.
    let destination = safeNextPath(searchParams.get("next"));
    if (!destination) {
      try {
        const profile = await apiFetch<Profile>("/me", { token: data.session.access_token });
        destination = HOME_BY_ROLE[profile.role];
      } catch {
        destination = "/";
      }
    }
    router.replace(stripLocale(destination));
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-4">
      {error ? <Alert tone="error">{t(`errors.${error}`)}</Alert> : null}
      <Field
        label={t("email")}
        name="email"
        type="email"
        autoComplete="email"
        required
        error={fieldError ?? undefined}
      />
      <Field
        label={t("password")}
        name="password"
        type="password"
        autoComplete="current-password"
        required
      />
      <Button type="submit" className="w-full" disabled={pending}>
        {pending ? t("submitting") : t("submitLogin")}
      </Button>
      <p className="text-center text-sm text-ink-muted">
        {t("noAccount")}{" "}
        <Link href="/signup" className="font-medium text-brand-700 hover:underline">
          {t("submitSignup")}
        </Link>
      </p>
    </form>
  );
}
