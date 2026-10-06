'use client';
import { useState, type FormEvent } from 'react';
import { supabase } from '@/lib/supabase';
export function DeleteAccount(){
 const [email,setEmail]=useState(''),[password,setPassword]=useState(''),[confirmed,setConfirmed]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 async function submit(event:FormEvent){event.preventDefault();if(!confirmed)return;setBusy(true);try{
  const {data,error}=await supabase.auth.signInWithPassword({email,password});if(error || !data.session)throw new Error('Sign in failed');
  const response=await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/v1/me`,{method:'DELETE',headers:{Authorization:`Bearer ${data.session.access_token}`}});
  if(!response.ok)throw new Error('Deletion request failed');
  await supabase.auth.signOut();setPassword('');setMessage('Your deletion request has been accepted.');
 }catch{setMessage('Unable to request deletion. Check your sign-in details or contact support.');}finally{setBusy(false);}}
 return <form onSubmit={submit} className="grid gap-4"><p>Deleting your Aventi account removes your saved events and preferences. Store subscriptions continue until cancelled separately.</p><a href="https://apps.apple.com/account/subscriptions">Manage Apple subscriptions</a><a href="https://play.google.com/store/account/subscriptions">Manage Google Play subscriptions</a><label>Email<input className="block w-full border p-3" type="email" required value={email} onChange={e=>setEmail(e.target.value)} autoComplete="email"/></label><label>Password<input className="block w-full border p-3" type="password" required value={password} onChange={e=>setPassword(e.target.value)} autoComplete="current-password"/></label><label><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/> I understand and want to delete my account.</label><button disabled={busy||!confirmed} className="border p-3">{busy?'Submitting…':'Delete account'}</button><p role="status">{message}</p></form>;
}
