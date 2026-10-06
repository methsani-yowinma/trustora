import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// jsdom does not implement scrolling.
Element.prototype.scrollTo ??= function scrollTo() {};

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

// Locale-aware navigation (next-intl) needs the Next.js router; components only use plain links
// and refresh/replace in these tests.
vi.mock("@/i18n/navigation", async () => {
  const { createElement } = await import("react");
  return {
    Link: ({ href, children, ...props }: { href: string; children: unknown }) =>
      createElement("a", { href, ...props }, children as never),
    useRouter: () => ({ refresh: vi.fn(), replace: vi.fn(), push: vi.fn() }),
    usePathname: () => "/",
    redirect: vi.fn(),
  };
});
