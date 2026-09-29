import Link from 'next/link';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Aventi Support',
  description: 'Contact Aventi support and find account and billing help.',
};

export default function SupportPage() {
  return (
    <main className="min-h-screen bg-[#0a100e] px-5 py-14 text-[#f8f6f0] sm:py-20">
      <div className="mx-auto max-w-3xl">
        <Link href="/" className="text-sm font-semibold text-[#e8c547] hover:underline">Aventi</Link>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight sm:text-5xl">Support</h1>
        <p className="mt-8 leading-7 text-white/75">For Aventi account, event, privacy, or subscription-access help, email <a className="text-[#e8c547] hover:underline" href="mailto:admin@crestcodecreative.com">admin@crestcodecreative.com</a>. Describe the issue and the email associated with your account if you have one. Never send a password, payment card number, or verification code.</p>
        <p className="mt-6 leading-7 text-white/75">Apple and Google handle subscription cancellation and payment refunds. You can manage a subscription in your device&apos;s store settings. To remove your Aventi account, use the app or the account-deletion page.</p>
        <nav aria-label="Aventi help" className="mt-10 flex flex-wrap gap-5 text-sm text-[#e8c547]">
          <Link href="/recover">Recover account</Link><Link href="/delete-account">Delete account</Link><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link>
        </nav>
      </div>
    </main>
  );
}
