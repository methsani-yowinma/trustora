import { ImageOff } from "lucide-react";

import { cn } from "@/lib/cn";

/**
 * User-uploaded images served from Supabase Storage. Uses a plain <img>: the files are already
 * validated and sized at upload, and this avoids coupling next/image config to the storage host.
 */
export function RemoteImage({
  src,
  alt,
  className,
}: {
  src: string | null | undefined;
  alt: string;
  className?: string;
}) {
  if (!src) {
    return (
      <div className={cn("flex items-center justify-center bg-canvas text-ink-muted", className)}>
        <ImageOff aria-hidden="true" className="h-6 w-6" />
      </div>
    );
  }
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={src} alt={alt} loading="lazy" className={cn("object-cover", className)} />;
}
