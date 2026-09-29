import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Delete an Aventi Account',
  description: 'Request deletion of your Aventi account and associated data.',
};

export default function DeleteAccountPage() {
  return (
    <main className="min-h-screen bg-[#0a100e] px-5 py-14 text-[#f8f6f0] sm:py-20">
      <article className="mx-auto max-w-3xl">
        <Link href="/" className="text-sm font-semibold text-[#e8c547] hover:underline">Aventi</Link>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight sm:text-5xl">Delete your Aventi account</h1>
        <p className="mt-8 leading-7 text-white/75">To request deletion outside the app, email <a className="text-[#e8c547] hover:underline" href="mailto:admin@crestcodecreative.com?subject=Aventi%20account%20deletion%20request">admin@crestcodecreative.com</a> with the subject “Aventi account deletion request.” Send it from your account email if possible. We may ask you to verify account ownership. Never send your password, verification code, or payment details.</p>
        <p className="mt-6 leading-7 text-white/75">You can also request deletion from Profile in the Aventi app. Deletion removes your Aventi profile and associated preferences, actions, favorites, and account data. A limited deletion record may remain to prevent recreation by an old sign-in token and document completion; other records may be retained where required for security, legal, or financial obligations.</p>
        <p className="mt-6 leading-7 text-white/75">Deleting your Aventi account does not cancel a subscription billed through Apple or Google. Cancel it separately in your store subscription settings to stop future charges.</p>
        <nav aria-label="Aventi help" className="mt-10 flex flex-wrap gap-5 text-sm text-[#e8c547]"><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link><Link href="/support">Support</Link></nav>
      </article>
    </main>
  );
}
