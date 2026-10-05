"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { clientApi } from "@/lib/api/browser";
import { useApiAction } from "@/lib/useApiAction";

export function CustomerOrderActions({ orderId, actions }: { orderId: string; actions: string[] }) {
  const t = useTranslations("orders");
  const { run, pending, error } = useApiAction();
  if (actions.length === 0) return null;

  return (
    <div className="space-y-3">
      {actions.includes("confirm_receipt") ? (
        <Button
          className="w-full"
          disabled={pending}
          onClick={() => run(() => clientApi(`/orders/${orderId}/confirm-receipt`, { method: "POST" }))}
        >
          {t("confirmReceipt")}
        </Button>
      ) : null}
      {actions.includes("cancel") ? (
        <Button
          variant="secondary"
          className="w-full"
          disabled={pending}
          onClick={() => {
            if (window.confirm(t("cancelConfirm"))) {
              void run(() => clientApi(`/orders/${orderId}/cancel`, { method: "POST" }));
            }
          }}
        >
          {t("cancel")}
        </Button>
      ) : null}
      {error ? <Alert tone="error">{error}</Alert> : null}
    </div>
  );
}

const NEEDS_REASON = new Set(["cancel", "failed"]);

export function SmeOrderActions({ orderId, actions }: { orderId: string; actions: string[] }) {
  const t = useTranslations("smeOrders");
  const tOrders = useTranslations("orders");
  const { run, pending, error } = useApiAction();
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string>();
  if (actions.length === 0) return null;

  function act(action: string) {
    if (NEEDS_REASON.has(action) && !reason.trim()) {
      setReasonError(t("reasonRequired"));
      return;
    }
    setReasonError(undefined);
    void run(() =>
      clientApi(`/sme/orders/${orderId}/status`, {
        method: "POST",
        body: { action, reason: NEEDS_REASON.has(action) ? reason.trim() : undefined },
      }),
    );
  }

  const primary = actions.filter((a) => !NEEDS_REASON.has(a));
  const withReason = actions.filter((a) => NEEDS_REASON.has(a));

  return (
    <div className="space-y-3">
      <h2 className="font-semibold">{t("actions")}</h2>
      {primary.map((action) => (
        <Button key={action} className="w-full" disabled={pending} onClick={() => act(action)}>
          {t(action as "confirm")}
        </Button>
      ))}
      {withReason.length > 0 ? (
        <div className="space-y-2 border-t border-line pt-3">
          <Field
            label={tOrders("reason")}
            name="reason"
            value={reason}
            maxLength={500}
            onChange={(e) => setReason(e.target.value)}
            error={reasonError}
          />
          {withReason.map((action) => (
            <Button key={action} variant="secondary" className="w-full" disabled={pending} onClick={() => act(action)}>
              {t(action as "cancel")}
            </Button>
          ))}
        </div>
      ) : null}
      <p className="text-xs text-ink-muted">{t("trustNote")}</p>
      {error ? <Alert tone="error">{error}</Alert> : null}
    </div>
  );
}
