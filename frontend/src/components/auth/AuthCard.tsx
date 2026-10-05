import type { ReactNode } from "react";

import { Card } from "@/components/ui/Card";
import { LogoMark } from "@/components/ui/Logo";

export function AuthCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  return (
    <div className="mx-auto max-w-md py-12 sm:py-16">
      <Card className="space-y-6 p-6 sm:p-8">
        <div className="space-y-2">
          <LogoMark className="h-10 w-10" />
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          <p className="text-ink-muted">{subtitle}</p>
        </div>
        {children}
      </Card>
    </div>
  );
}
