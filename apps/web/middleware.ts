import { type NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (!pathname.startsWith('/admin')) {
    return NextResponse.next();
  }

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!supabaseUrl || !supabaseAnonKey) {
    return NextResponse.redirect(new URL('/', request.url));
  }

  const supabase = createClient(supabaseUrl, supabaseAnonKey, {
    auth: { persistSession: false },
    global: {
      headers: {
        cookie: request.headers.get('cookie') ?? '',
      },
    },
  });

  const {
    data: { user },
    error,
  } = await supabase.auth.getUser();

  if (error) {
    console.error('Auth validation error:', error.message);
    return NextResponse.redirect(new URL('/', request.url));
  }

  if (!user) {
    return NextResponse.redirect(new URL('/', request.url));
  }

  const meta = user.app_metadata ?? {};
  const role: string = meta.role ?? '';
  const roles: string[] = meta.roles ?? [];
  const isAdmin =
    role === 'admin' || role === 'aventi_admin' || role === 'owner' ||
    roles.includes('admin') || roles.includes('aventi_admin') || roles.includes('owner');

  if (!isAdmin) {
    return NextResponse.redirect(new URL('/', request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/admin/:path*'],
};
