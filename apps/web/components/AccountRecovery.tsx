'use client';
import { useEffect, useState, type FormEvent } from 'react';
import { supabase } from '@/lib/supabase';
export function AccountRecovery() {
  const [email,setEmail]=useState('');
  const [password,setPassword]=useState('');
  const [ready,setReady]=useState(false);
  const [message,setMessage]=useState('');
  const [busy,setBusy]=useState(false);
  useEffect(() => {
    let active=true;
    const {data:{subscription}}=supabase.auth.onAuthStateChange((event) => { if(active && event==='PASSWORD_RECOVERY') setReady(true); });
    const code=new URL(window.location.href).searchParams.get('code');
    if(code) void supabase.auth.exchangeCodeForSession(code).then(({error})=>{ if(active){setReady(!error);if(error)setMessage('Recovery link expired. Request a new one.');} window.history.replaceState({},'', '/recover'); });
    return ()=>{active=false;subscription.unsubscribe();};
  },[]);
  async function submit(event:FormEvent){event.preventDefault();setBusy(true);try{
    const {error}=ready ? await supabase.auth.updateUser({password}) : await supabase.auth.resetPasswordForEmail(email,{redirectTo:`${window.location.origin}/recover`});
    if(error) throw error;
    setMessage(ready?'Password updated. You can sign in to Aventi.':'If an account exists, a recovery email is on its way.');
    if(ready) await supabase.auth.signOut();
  }catch{setMessage('Unable to complete recovery. Try again or contact support.');}finally{setBusy(false);}}
  return <form onSubmit={submit} className="grid gap-4"><label>{ready?'New password':'Email'}<input className="block w-full border p-3" required type={ready?'password':'email'} minLength={ready?8:undefined} value={ready?password:email} onChange={e=>ready?setPassword(e.target.value):setEmail(e.target.value)} autoComplete={ready?'new-password':'email'}/></label><button disabled={busy} className="border p-3">{busy?'Working…':ready?'Update password':'Send recovery email'}</button><p role="status">{message}</p></form>;
}
