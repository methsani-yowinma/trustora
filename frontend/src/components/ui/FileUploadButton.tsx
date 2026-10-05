"use client";

import { Upload } from "lucide-react";
import { useRef } from "react";

import { buttonClasses } from "./Button";

/** Accessible file picker styled as a button. Server-side validation is authoritative. */
export function FileUploadButton({
  label,
  accept,
  disabled,
  onSelect,
}: {
  label: string;
  accept: string;
  disabled?: boolean;
  onSelect: (file: File) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <input
        ref={input}
        type="file"
        accept={accept}
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) onSelect(file);
        }}
      />
      <button
        type="button"
        disabled={disabled}
        onClick={() => input.current?.click()}
        className={buttonClasses("secondary")}
      >
        <Upload aria-hidden="true" className="h-4 w-4" />
        {label}
      </button>
    </>
  );
}

export const IMAGE_ACCEPT = "image/jpeg,image/png,image/webp";
export const DOCUMENT_ACCEPT = "application/pdf,image/jpeg,image/png,image/webp";
