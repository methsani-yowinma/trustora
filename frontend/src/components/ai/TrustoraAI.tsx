"use client";

import { ArrowUp, Package, RotateCcw, ShoppingBag, Store, X } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";

import { Link } from "@/i18n/navigation";
import { ApiError } from "@/lib/api/client";
import { clientApi } from "@/lib/api/browser";
import type { ChatResponse, ChatSource, ComplaintDraft } from "@/lib/api/types";
import { cn } from "@/lib/cn";

import { ComplaintDraftCard } from "./ComplaintDraftCard";
import { TrustoraAiMark } from "./TrustoraAiMark";

type Message = {
  id: number;
  role: "user" | "assistant";
  text: string;
  sources?: ChatSource[];
  draft?: ComplaintDraft | null;
};

type SuggestionKey =
  | "storeTrust"
  | "storeScore"
  | "productVerified"
  | "productSeller"
  | "whereOrder"
  | "howScore"
  | "myScore"
  | "improve"
  | "problem";

// The API accepts at most 12 turns of up to 1000 characters; the last one must be the user's.
const MAX_TURNS = 12;
const MAX_CHARS = 1000;

/** The conversation as the API accepts it: the most recent turns, each within the length limit. */
export function chatTurns(history: Pick<Message, "role" | "text">[]) {
  return history.slice(-MAX_TURNS).map((m) => ({ role: m.role, text: m.text.slice(0, MAX_CHARS) }));
}

/** What the user is looking at, so "this seller" / "this product" means something. */
export function pageContext(pathname: string) {
  const store = pathname.match(/^\/[a-z]{2}\/stores\/([A-Za-z0-9-]{3,40})(?:\/|$)/);
  const product = pathname.match(/^\/[a-z]{2}\/products\/([0-9a-f-]{36})(?:\/|$)/i);
  const section = pathname.split("/")[2] ?? "";
  return {
    context: store ? { store_slug: store[1] } : product ? { product_id: product[1] } : undefined,
    suggestions: (store
      ? ["storeTrust", "storeScore", "whereOrder"]
      : product
        ? ["productVerified", "productSeller", "whereOrder"]
        : section === "sme"
          ? ["myScore", "improve", "howScore"]
          : ["whereOrder", "problem", "howScore"]) as SuggestionKey[],
  };
}

const SOURCE_ICON = { STORE: Store, PRODUCT: ShoppingBag, ORDER: Package } as const;

function sourceHref(source: ChatSource) {
  if (source.kind === "STORE") return `/stores/${source.ref}/passport`;
  if (source.kind === "PRODUCT") return `/products/${source.ref}`;
  return `/orders/${source.ref}`;
}

export function TrustoraAI() {
  const t = useTranslations("chat");
  const tErrors = useTranslations("apiErrors");
  const locale = useLocale();
  const pathname = usePathname();
  const { context, suggestions } = pageContext(pathname);

  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nextId = useRef(1);
  const launcherRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

  const wasOpen = useRef(false);
  const close = useCallback(() => setOpen(false), []);

  // Return focus to the launcher after closing (once it is visible again: on phones it is hidden
  // while the panel is open).
  useEffect(() => {
    if (wasOpen.current && !open) launcherRef.current?.focus();
    wasOpen.current = open;
  }, [open]);

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    // On the document, not the panel: focus may be on <body> after a suggestion chip unmounts.
    const onKey = (event: globalThis.KeyboardEvent) => event.key === "Escape" && close();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, close]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, pending]);

  async function send(text: string) {
    const question = text.trim().slice(0, MAX_CHARS);
    if (!question || pending) return;
    const userMessage: Message = { id: nextId.current++, role: "user", text: question };
    const history = [...messages, userMessage];
    setMessages(history);
    setInput("");
    setError(null);
    setPending(true);
    try {
      const response = await clientApi<ChatResponse>("/chat", {
        method: "POST",
        body: {
          messages: chatTurns(history),
          locale,
          context,
        },
      });
      setMessages((current) => [
        ...current,
        {
          id: nextId.current++,
          role: "assistant",
          text: response.reply,
          sources: response.sources,
          draft: response.draft,
        },
      ]);
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "generic";
      setError(
        code === "ai_unavailable"
          ? t("unavailable")
          : tErrors.has(code as Parameters<typeof tErrors>[0])
            ? tErrors(code as Parameters<typeof tErrors>[0])
            : tErrors("generic"),
      );
      // Let the user edit and resend the question that failed.
      setMessages((current) => current.filter((m) => m.id !== userMessage.id));
      setInput(question);
    } finally {
      setPending(false);
      inputRef.current?.focus();
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void send(input);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send(input);
    }
  }

  return (
    <>
      <button
        ref={launcherRef}
        type="button"
        onClick={() => (open ? close() : setOpen(true))}
        aria-expanded={open}
        aria-controls={open ? `${titleId}-panel` : undefined}
        aria-label={open ? t("close") : t("open")}
        title={t("name")}
        className={cn(
          "fixed right-4 bottom-4 z-50 grid h-14 w-14 place-items-center rounded-2xl bg-ink shadow-lg ring-1 ring-white/10 transition-transform hover:-translate-y-0.5 sm:right-6 sm:bottom-6",
          open && "max-sm:hidden",
        )}
      >
        {open ? <X aria-hidden="true" className="h-6 w-6 text-white" /> : <TrustoraAiMark animated className="h-8 w-8" />}
      </button>

      {open ? (
        <section
          id={`${titleId}-panel`}
          role="dialog"
          aria-labelledby={titleId}
          className="fixed inset-x-0 bottom-0 z-50 flex h-[min(88dvh,640px)] flex-col overflow-hidden rounded-t-2xl border border-line bg-surface shadow-2xl sm:inset-x-auto sm:right-6 sm:bottom-24 sm:h-[min(600px,calc(100dvh-8rem))] sm:w-[400px] sm:rounded-2xl"
        >
          <header className="flex items-center gap-3 bg-ink px-4 py-3 text-white">
            <TrustoraAiMark className="h-8 w-8 shrink-0" />
            <div className="min-w-0 flex-1">
              <h2 id={titleId} className="font-semibold leading-tight">
                {t("name")}
              </h2>
              <p className="truncate text-xs text-white/70">{t("tagline")}</p>
            </div>
            {messages.length > 0 ? (
              <button
                type="button"
                onClick={() => {
                  setMessages([]);
                  setError(null);
                }}
                className="rounded-lg p-2 text-white/80 hover:bg-white/10 hover:text-white"
                aria-label={t("newChat")}
                title={t("newChat")}
              >
                <RotateCcw aria-hidden="true" className="h-4 w-4" />
              </button>
            ) : null}
            <button
              type="button"
              onClick={close}
              className="rounded-lg p-2 text-white/80 hover:bg-white/10 hover:text-white"
              aria-label={t("close")}
            >
              <X aria-hidden="true" className="h-5 w-5" />
            </button>
          </header>

          <div ref={logRef} role="log" aria-live="polite" className="flex-1 space-y-3 overflow-y-auto bg-canvas px-4 py-4">
            <AssistantBubble>{t("greeting")}</AssistantBubble>

            {messages.length === 0 ? (
              <div className="space-y-2 pl-9">
                <p className="text-xs font-medium text-ink-muted">{t("suggestionsLabel")}</p>
                <ul className="flex flex-wrap gap-2">
                  {suggestions.map((key) => (
                    <li key={key}>
                      <button
                        type="button"
                        onClick={() => void send(t(`suggest.${key}`))}
                        className="rounded-full border border-brand-100 bg-surface px-3 py-1.5 text-left text-sm text-brand-700 hover:border-brand-500 hover:bg-brand-50"
                      >
                        {t(`suggest.${key}`)}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {messages.map((message) =>
              message.role === "user" ? (
                <div key={message.id} className="flex justify-end">
                  <p className="max-w-[85%] rounded-2xl rounded-br-md bg-brand-600 px-3.5 py-2 text-sm whitespace-pre-line text-white">
                    <span className="sr-only">{t("you")}: </span>
                    {message.text}
                  </p>
                </div>
              ) : (
                <div key={message.id} className="space-y-2">
                  <AssistantBubble>{message.text}</AssistantBubble>
                  {message.sources && message.sources.length > 0 ? (
                    <div className="flex flex-wrap items-center gap-1.5 pl-9">
                      <span className="text-xs text-ink-muted">{t("sources")}:</span>
                      {message.sources.map((source) => {
                        const Icon = SOURCE_ICON[source.kind];
                        return (
                          <Link
                            key={`${source.kind}-${source.ref}`}
                            href={sourceHref(source)}
                            className="inline-flex max-w-full items-center gap-1 rounded-full border border-line bg-surface px-2.5 py-1 text-xs text-ink hover:border-brand-500 hover:text-brand-700"
                          >
                            <Icon aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
                            <span className="truncate">{t(`source.${source.kind}`, { label: source.label })}</span>
                          </Link>
                        );
                      })}
                    </div>
                  ) : null}
                  {message.draft ? (
                    <div className="pl-9">
                      <ComplaintDraftCard draft={message.draft} />
                    </div>
                  ) : null}
                </div>
              ),
            )}

            {pending ? (
              <div className="flex items-center gap-2 pl-9 text-sm text-ink-muted" role="status">
                <span className="flex gap-1" aria-hidden="true">
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-500 [animation-delay:-0.3s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-500 [animation-delay:-0.15s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-500" />
                </span>
                {t("thinking")}
              </div>
            ) : null}

            {error ? (
              <p role="alert" className="rounded-lg border border-trust-risk/30 bg-trust-risk/5 px-3 py-2 text-sm text-trust-risk">
                {error}
              </p>
            ) : null}
          </div>

          <form onSubmit={onSubmit} className="border-t border-line bg-surface p-3">
            <div className="flex items-end gap-2 rounded-xl border border-line bg-surface px-3 py-2 focus-within:border-brand-500 focus-within:ring-2 focus-within:ring-brand-100">
              <label htmlFor={`${titleId}-input`} className="sr-only">
                {t("inputLabel")}
              </label>
              <textarea
                id={`${titleId}-input`}
                ref={inputRef}
                rows={1}
                maxLength={MAX_CHARS}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder={t("placeholder")}
                className="max-h-28 min-h-6 flex-1 resize-none bg-transparent text-sm outline-none placeholder:text-ink-muted [field-sizing:content]"
                data-chat-input
              />
              <button
                type="submit"
                disabled={pending || !input.trim()}
                aria-label={t("send")}
                className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-brand-600 text-white hover:bg-brand-700 disabled:bg-line disabled:text-ink-muted"
              >
                <ArrowUp aria-hidden="true" className="h-4 w-4" />
              </button>
            </div>
            <p className="mt-2 text-[11px] leading-snug text-ink-muted">{t("disclaimer")}</p>
          </form>
        </section>
      ) : null}
    </>
  );
}

function AssistantBubble({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-2">
      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-ink">
        <TrustoraAiMark className="h-5 w-5" />
      </span>
      <p className="max-w-[85%] rounded-2xl rounded-tl-md border border-line bg-surface px-3.5 py-2 text-sm whitespace-pre-line">
        {children}
      </p>
    </div>
  );
}
