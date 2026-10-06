import assert from 'node:assert/strict';
import test from 'node:test';
import type { User } from '@supabase/supabase-js';
import { isAdminUser } from '../lib/admin-access';
test('only server-controlled metadata grants administration', () => {
  assert.equal(isAdminUser(null), false);
  for (const fields of [{is_admin:true},{role:'admin'},{roles:['owner']}]) {
    assert.equal(isAdminUser({ id:'test', aud:'authenticated', created_at:'2026-01-01', user_metadata:fields, app_metadata:{} } as User),false);
    assert.equal(isAdminUser({ id:'test', aud:'authenticated', created_at:'2026-01-01', user_metadata:{}, app_metadata:fields } as User),true);
  }
});
