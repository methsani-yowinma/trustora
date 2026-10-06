"use client";

import { useSyncExternalStore } from "react";

import type { LocalizedText } from "@/lib/api/types";

/**
 * Client-side cart: one store at a time (approved MVP decision). It only remembers product ids,
 * quantities and display snapshots — prices and stock are always re-checked by the API quote.
 * Stored in localStorage; reads/writes are wrapped because storage can be unavailable.
 */
export type CartLine = {
  productId: string;
  quantity: number;
  name: LocalizedText;
  priceLkr: string;
  imageUrl: string | null;
  maxQuantity: number;
};

export type Cart = { store: { id: string; slug: string; name: string }; lines: CartLine[] } | null;

const KEY = "trustora.cart.v1";
const EVENT = "trustora-cart";
const MAX_LINES = 20;

let cached: { raw: string | null; value: Cart } = { raw: null, value: null };

function read(): Cart {
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
  if (raw === cached.raw) return cached.value;
  let value: Cart = null;
  try {
    value = raw ? (JSON.parse(raw) as Cart) : null;
  } catch {
    value = null;
  }
  cached = { raw, value };
  return value;
}

function write(cart: Cart) {
  try {
    if (cart && cart.lines.length) window.localStorage.setItem(KEY, JSON.stringify(cart));
    else window.localStorage.removeItem(KEY);
  } catch {
    // Storage unavailable (private mode, blocked): the cart lives only for this page view.
  }
  window.dispatchEvent(new Event(EVENT));
}

function subscribe(callback: () => void) {
  window.addEventListener(EVENT, callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener(EVENT, callback);
    window.removeEventListener("storage", callback);
  };
}

export function useCart(): Cart {
  return useSyncExternalStore(subscribe, read, () => null);
}

export function cartCount(cart: Cart): number {
  return cart ? cart.lines.reduce((sum, line) => sum + line.quantity, 0) : 0;
}

/** Adds a product. Returns "store_conflict" (without changing the cart) if it is from another store. */
export function addToCart(
  store: NonNullable<Cart>["store"],
  line: CartLine,
  { replace = false }: { replace?: boolean } = {},
): "added" | "store_conflict" {
  const cart = read();
  if (cart && cart.store.id !== store.id && !replace) return "store_conflict";

  const base = cart && cart.store.id === store.id ? cart : { store, lines: [] };
  const existing = base.lines.find((l) => l.productId === line.productId);
  const lines = existing
    ? base.lines.map((l) =>
        l.productId === line.productId
          ? { ...line, quantity: Math.min(l.quantity + line.quantity, line.maxQuantity) }
          : l,
      )
    : [...base.lines, line].slice(0, MAX_LINES);
  write({ store, lines });
  return "added";
}

export function setQuantity(productId: string, quantity: number) {
  const cart = read();
  if (!cart) return;
  write({
    ...cart,
    lines: cart.lines
      .map((l) => (l.productId === productId ? { ...l, quantity: Math.min(quantity, l.maxQuantity) } : l))
      .filter((l) => l.quantity > 0),
  });
}

export function removeFromCart(productId: string) {
  setQuantity(productId, 0);
}

export function clearCart() {
  write(null);
}
