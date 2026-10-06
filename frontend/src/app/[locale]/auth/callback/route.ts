import { NextResponse, type NextRequest } from "next/server";

import { createClient } from "@/lib/supabase/server";

/** Email-confirmation landing: exchanges the PKCE code for a session cookie. */
export async function GET(
  request: NextRequest,
  { params }: RouteContext<"/[locale]/auth/callback">,
) {
  const { locale } = await params;
  const code = request.nextUrl.searchParams.get("code");
  const origin = request.nextUrl.origin;

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      return NextResponse.redirect(`${origin}/${locale}`);
    }
  }
  return NextResponse.redirect(`${origin}/${locale}/login?error=callback`);
}
