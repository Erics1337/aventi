import { DeleteAccount } from '@/components/DeleteAccount';
import Link from 'next/link';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Delete an Aventi Account',
  description: 'Request deletion of your Aventi account and associated data.',
};

export default function DeletePage() {
  return <main className="min-h-screen bg-[#0a100e] px-5 py-14 text-[#f8f6f0] sm:py-20"><div className="mx-auto max-w-3xl"><Link href="/" className="text-sm font-semibold text-[#e8c547] hover:underline">Aventi</Link><h1 className="mt-3 text-4xl font-semibold tracking-tight sm:text-5xl">Delete your Aventi account</h1><p className="mt-8 leading-7 text-white/75">Use the app&apos;s Profile screen to request deletion, or sign in below. If you cannot access either, email <a className="text-[#e8c547] hover:underline" href="mailto:admin@crestcodecreative.com?subject=Aventi%20account%20deletion%20request">admin@crestcodecreative.com</a> from your account email if possible. We may need to verify account ownership. Never send your password or payment details.</p><div className="mt-8"><DeleteAccount /></div><p className="mt-8 leading-7 text-white/70">Deletion removes your Aventi profile and associated preferences, actions, favorites, and account data. A limited deletion record may remain to prevent recreation by an old sign-in token and document completion; other records may be retained where required for security, legal, or financial obligations. <Link className="text-[#e8c547] hover:underline" href="/privacy">Read the Privacy Policy</Link>.</p></div></main>;
}
