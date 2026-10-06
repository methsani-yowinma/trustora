import { renderHook, act } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { addToCart, cartCount, clearCart, removeFromCart, setQuantity, useCart, type CartLine } from "./cart";

const ceylon = { id: "s1", slug: "ceylon-crafts", name: "Ceylon Crafts" };
const matale = { id: "s2", slug: "matale-spice", name: "Matale Spice Garden" };

function line(productId: string, quantity = 1, maxQuantity = 5): CartLine {
  return { productId, quantity, name: { en: productId }, priceLkr: "100.00", imageUrl: null, maxQuantity };
}

describe("cart", () => {
  it("holds products from one store at a time", () => {
    const { result } = renderHook(() => useCart());
    act(() => {
      expect(addToCart(ceylon, line("saree"))).toBe("added");
    });
    let outcome: string | undefined;
    act(() => {
      outcome = addToCart(matale, line("cinnamon"));
    });
    expect(outcome).toBe("store_conflict");
    expect(result.current?.store.slug).toBe("ceylon-crafts");

    act(() => {
      addToCart(matale, line("cinnamon"), { replace: true });
    });
    expect(result.current?.store.slug).toBe("matale-spice");
    expect(result.current?.lines.map((l) => l.productId)).toEqual(["cinnamon"]);
  });

  it("never exceeds the available quantity", () => {
    const { result } = renderHook(() => useCart());
    act(() => {
      addToCart(ceylon, line("saree", 3, 4));
      addToCart(ceylon, line("saree", 3, 4));
    });
    expect(result.current?.lines[0].quantity).toBe(4);
    act(() => setQuantity("saree", 99));
    expect(result.current?.lines[0].quantity).toBe(4);
    expect(cartCount(result.current)).toBe(4);
  });

  it("removes lines and empties", () => {
    const { result } = renderHook(() => useCart());
    act(() => {
      addToCart(ceylon, line("saree"));
      addToCart(ceylon, line("box"));
      removeFromCart("saree");
    });
    expect(result.current?.lines.map((l) => l.productId)).toEqual(["box"]);
    act(() => clearCart());
    expect(result.current).toBeNull();
    expect(cartCount(result.current)).toBe(0);
  });

  it("ignores corrupted storage", () => {
    window.localStorage.setItem("trustora.cart.v1", "{not json");
    const { result } = renderHook(() => useCart());
    expect(result.current).toBeNull();
  });
});
