import { notFound } from "next/navigation";

// Routes unknown paths under /[locale] to the localized not-found page.
export default function CatchAll() {
  notFound();
}
