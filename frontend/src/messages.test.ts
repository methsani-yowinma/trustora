import { describe, expect, it } from "vitest";

import en from "../messages/en.json";
import si from "../messages/si.json";

type Tree = { [key: string]: string | Tree };

function flatten(tree: Tree, prefix = ""): Record<string, string> {
  return Object.entries(tree).reduce<Record<string, string>>((out, [key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return typeof value === "string" ? { ...out, [path]: value } : { ...out, ...flatten(value, path) };
  }, {});
}

/** ICU argument names, e.g. "{count, plural, …}" → count, "{store}" → store. */
function placeholders(message: string): string[] {
  const names = new Set<string>();
  for (const match of message.matchAll(/\{\s*([A-Za-z_][\w]*)\s*(?:,|\})/g)) names.add(match[1]);
  return [...names].sort();
}

const english = flatten(en as Tree);
const sinhala = flatten(si as Tree);

describe("translations", () => {
  it("Sinhala has exactly the English keys", () => {
    expect(Object.keys(sinhala).sort()).toEqual(Object.keys(english).sort());
  });

  it("no message is empty", () => {
    const empty = Object.entries({ ...english, ...sinhala }).filter(([, v]) => !v.trim());
    expect(empty).toEqual([]);
  });

  it("every message uses the same placeholders in both languages", () => {
    const mismatched = Object.keys(english).filter(
      (key) => placeholders(english[key]).join() !== placeholders(sinhala[key]).join(),
    );
    expect(mismatched).toEqual([]);
  });

  it("absolute safety wording only ever appears negated (disclaimers)", () => {
    const absolute = /100\s*%|guarantee|completely safe|risk[- ]free/i;
    const negated = /\bnever\b|\bnot\b|\bno\b/i;
    const claims = Object.entries(english).filter(([, v]) => absolute.test(v) && !negated.test(v));
    expect(claims).toEqual([]);
  });
});
