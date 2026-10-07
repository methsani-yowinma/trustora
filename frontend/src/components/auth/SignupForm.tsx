"use client";

import { ShoppingBag, Store } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { type FormEvent, useState } from "react";
import { z } from "zod";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Link, useRouter } from "@/i18n/navigation";
import { cn } from "@/lib/cn";
import { createClient } from "@/lib/supabase/client";

import { type AuthErrorKey, authErrorKey } from "./authErrors";

type AccountType = "CUSTOMER" | "SME";

const schema = z.object({
  fullName: z.string().trim().min(1).max(120),
  email: z.email(),
  password: z.string().min(8).max(72),
});

type FieldErrors = Partial<Record<"fullName" | "email" | "password", string>>;

export function SignupForm() {
  const t = useTranslations("auth");
  const locale = useLocale();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [accountType, setAccountType] = useState<AccountType>(
    searchParams.get("type") === "sme" ? "SME" : "CUSTOMER",
  );
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<AuthErrorKey | null>(null);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const form = new FormData(event.currentTarget);
    const parsed = schema.safeParse({
      fullName: form.get("fullName"),
      email: form.get("email"),
      password: form.get("password"),
    });
    if (!parsed.success) {
      const invalid = new Set(parsed.error.issues.map((issue) => issue.path[0]));
      setFieldErrors({
        fullName: invalid.has("fullName") ? t("errors.nameRequired") : undefined,
        email: invalid.has("email") ? t("errors.invalidEmail") : undefined,
        password: invalid.has("password") ? t("errors.passwordTooShort") : undefined,
      });
      return;
    }
    setFieldErrors({});
    setPending(true);

    const { fullName, email, password } = parsed.data;
    const { data, error: signUpError } = await createClient().auth.signUp({
      email,
      password,
      options: {
        // Only CUSTOMER/SME are honoured by the database trigger; ADMIN is never self-assignable.
        data: { full_name: fullName, role: accountType, locale },
        emailRedirectTo: `${window.location.origin}/${locale}/auth/callback`,
      },
    });
    setPending(false);

    if (signUpError) {
      setError(authErrorKey(signUpError));
      return;
    }
    if (data.session) {
      router.replace(accountType === "SME" ? "/sme" : "/");
      router.refresh();
      return;
    }
    setSentTo(email);
  }

  if (sentTo) {
    return (
      <Alert tone="success" title={t("checkEmailTitle")}>
        {t("checkEmailBody", { email: sentTo })}
      </Alert>
    );
  }

  const options = [
    {
      value: "CUSTOMER" as const,
      label: t("accountTypeCustomer"),
      hint: t("accountTypeCustomerHint"),
      Icon: ShoppingBag,
    },
    { value: "SME" as const, label: t("accountTypeSme"), hint: t("accountTypeSmeHint"), Icon: Store },
  ];

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-4">
      {error ? <Alert tone="error">{t(`errors.${error}`)}</Alert> : null}

      <fieldset>
        <legend className="mb-1.5 text-sm font-medium">{t("accountType")}</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {options.map(({ value, label, hint, Icon }) => (
            <label
              key={value}
              className={cn(
                "flex cursor-pointer flex-col gap-1 rounded-lg border p-3 text-sm transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-brand-600",
                accountType === value ? "border-brand-600 bg-brand-50" : "border-line hover:bg-canvas",
              )}
            >
              <input
                type="radio"
                name="accountType"
                value={value}
                checked={accountType === value}
                onChange={() => setAccountType(value)}
                className="sr-only"
              />
              <span className="flex items-center gap-2 font-medium">
                <Icon aria-hidden="true" className="h-4 w-4 text-brand-600" />
                {label}
              </span>
              <span className="text-ink-muted">{hint}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <Field
        label={t("fullName")}
        name="fullName"
        autoComplete="name"
        required
        error={fieldErrors.fullName}
      />
      <Field
        label={t("email")}
        name="email"
        type="email"
        autoComplete="email"
        required
        error={fieldErrors.email}
      />
      <Field
        label={t("password")}
        name="password"
        type="password"
        autoComplete="new-password"
        required
        hint={t("passwordHint")}
        error={fieldErrors.password}
      />
      <Button type="submit" className="w-full" disabled={pending}>
        {pending ? t("submitting") : t("submitSignup")}
      </Button>
      <p className="text-center text-sm text-ink-muted">
        {t("haveAccount")}{" "}
        <Link href="/login" className="font-medium text-brand-700 hover:underline">
          {t("submitLogin")}
        </Link>
      </p>
    </form>
  );
}
