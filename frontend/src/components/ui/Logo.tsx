import { cn } from "@/lib/cn";

/** Trustora mark: a shield with a verification tick and a small "signal" node. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={cn("h-8 w-8", className)}>
      <path
        d="M16 2.5 4.5 7v8.2c0 7.1 4.9 12.3 11.5 14.3 6.6-2 11.5-7.2 11.5-14.3V7L16 2.5Z"
        fill="var(--color-brand-600)"
      />
      <path
        d="m10.5 16.2 3.8 3.8 7.4-7.6"
        fill="none"
        stroke="#fff"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="24.5" cy="6.5" r="3" fill="var(--color-brand-100)" stroke="var(--color-brand-700)" strokeWidth="1.5" />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <LogoMark />
      <span className="text-lg font-semibold tracking-tight text-ink">Trustora</span>
    </span>
  );
}
