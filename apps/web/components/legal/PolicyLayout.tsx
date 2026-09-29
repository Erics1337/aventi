import Link from 'next/link';

export type PolicySection = { title: string; paragraphs: string[] };

export function PolicyLayout({ title, intro, sections }: { title: string; intro: string; sections: PolicySection[] }) {
  return (
    <main className="min-h-screen bg-[#0a100e] px-5 py-14 text-[#f8f6f0] sm:py-20">
      <article className="mx-auto max-w-3xl">
        <Link href="/" className="text-sm font-semibold text-[#e8c547] hover:underline">Aventi</Link>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight sm:text-5xl">{title}</h1>
        <p className="mt-3 text-sm text-white/55">Last updated: September 28, 2026</p>
        <p className="mt-8 text-lg leading-8 text-white/75">{intro}</p>
        <div className="mt-12 space-y-10">
          {sections.map((section) => (
            <section key={section.title}>
              <h2 className="text-2xl font-semibold">{section.title}</h2>
              {section.paragraphs.map((paragraph) => <p key={paragraph} className="mt-4 leading-7 text-white/70">{paragraph}</p>)}
            </section>
          ))}
        </div>
        <p className="mt-12 border-t border-white/15 pt-6 leading-7 text-white/70">
          Questions? Email <a className="text-[#e8c547] hover:underline" href="mailto:admin@crestcodecreative.com">admin@crestcodecreative.com</a>.
        </p>
        <nav aria-label="Aventi help and policies" className="mt-6 flex flex-wrap gap-5 text-sm text-[#e8c547]">
          <Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link><Link href="/support">Support</Link><Link href="/delete-account">Delete account</Link>
        </nav>
      </article>
    </main>
  );
}
