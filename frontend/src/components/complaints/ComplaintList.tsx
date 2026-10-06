import { useLocale, useTranslations } from "next-intl";

import { Card } from "@/components/ui/Card";
import { Link } from "@/i18n/navigation";
import type { ComplaintStatus, ComplaintSummary } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/localize";

import { ComplaintStatusBadge } from "./ComplaintThread";

export function ComplaintList({
  items,
  basePath,
  emptyText,
}: {
  items: ComplaintSummary[];
  basePath: "/sme/complaints" | "/admin/complaints";
  emptyText: string;
}) {
  const tCategory = useTranslations("complaintCategory");
  const tOrders = useTranslations("orders");
  const locale = useLocale();
  if (items.length === 0) return <Card className="text-center text-ink-muted">{emptyText}</Card>;

  return (
    <ul className="space-y-3">
      {items.map((item) => (
        <li key={item.id}>
          <Link href={`${basePath}/${item.id}`} className="block">
            <Card className="flex flex-wrap items-center justify-between gap-3 p-4 transition-shadow hover:shadow-md">
              <div className="space-y-1">
                <p className="font-medium">
                  {tCategory(item.category)} · {item.store_name}
                </p>
                <p className="text-sm text-ink-muted">
                  {tOrders("order", { number: item.order_number })} · {formatDate(item.created_at, locale)}
                </p>
              </div>
              <ComplaintStatusBadge status={item.status} />
            </Card>
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function StatusFilter({
  basePath,
  statuses,
  current,
  allLabel,
  label,
  labelFor,
}: {
  basePath: "/sme/complaints" | "/admin/complaints";
  statuses: ComplaintStatus[];
  current: ComplaintStatus | undefined;
  allLabel?: string;
  label: string;
  labelFor: (status: ComplaintStatus) => string;
}) {
  const options: (ComplaintStatus | undefined)[] = allLabel ? [undefined, ...statuses] : statuses;
  return (
    <nav aria-label={label} className="flex flex-wrap gap-2">
      {options.map((status) => (
        <Link
          key={status ?? "all"}
          href={status ? { pathname: basePath, query: { status } } : basePath}
          aria-current={status === current ? "page" : undefined}
          className={cn(
            "rounded-full border px-3 py-1 text-sm",
            status === current ? "border-brand-600 bg-brand-50 text-brand-700" : "border-line text-ink-muted",
          )}
        >
          {status ? labelFor(status) : allLabel}
        </Link>
      ))}
    </nav>
  );
}
