import type { User } from '@supabase/supabase-js';

const ADMIN_ROLES = new Set(['admin', 'aventi_admin', 'owner']);

function roleIsAdmin(value: unknown): boolean {
  return typeof value === 'string' && ADMIN_ROLES.has(value.toLowerCase());
}

function rolesIncludeAdmin(value: unknown): boolean {
  return (
    Array.isArray(value) &&
    value.some((item) => typeof item === 'string' && ADMIN_ROLES.has(item.toLowerCase()))
  );
}

/**
 * Matches backend `auth._claims_include_admin` / typical Supabase JWT shapes so UI and middleware
 * agree on who can see Admin Portal using server-controlled app_metadata only.
 */
export function isAdminUser(user: User | null | undefined): boolean {
  if (!user) return false;
  const app = user.app_metadata as Record<string, unknown> | undefined;

  if (app?.is_admin === true) return true;
  if (roleIsAdmin(app?.role)) return true;
  if (rolesIncludeAdmin(app?.roles)) return true;
  return false;
}
