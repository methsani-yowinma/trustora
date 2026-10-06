const PROBE_ORIGIN = "https://trustora.invalid";

/**
 * Only allow same-site relative paths as post-login redirects (prevents open redirects).
 *
 * Browsers strip tabs/newlines from URLs and treat "\" like "/", so "/\t/evil.com" or "/\evil.com"
 * would become "//evil.com". Such input is rejected, and the result must resolve to our own origin.
 */
export function safeNextPath(value: string | null | undefined): string | null {
  if (!value || value.length > 2048 || !value.startsWith("/") || /[\u0000-\u001f\u007f\\]/.test(value)) {
    return null;
  }
  if (value.startsWith("//")) return null;
  try {
    const url = new URL(value, PROBE_ORIGIN);
    if (url.origin !== PROBE_ORIGIN) return null;
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return null;
  }
}
