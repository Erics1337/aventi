import AsyncStorage from '@react-native-async-storage/async-storage'
import { createClient } from '@supabase/supabase-js'

const supabaseUrl = 'https://pnrmmsuhjisvpnejjbhe.supabase.co'
const supabaseAnonKey =
	'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBucm1tc3VoamlzdnBuZWpqYmhlIiwicm9sZSI6ImFub24iLCJpYXQiOjE2NTQyMjE3MjQsImV4cCI6MTk2OTc5NzcyNH0.P_NhKyxoyEda97bx4XqpYvZceqc3pxWOWCeFwKoV8aE'

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
	localStorage: AsyncStorage as any,
	autoRefreshToken: true,
	persistSession: true,
	detectSessionInUrl: false,
})
