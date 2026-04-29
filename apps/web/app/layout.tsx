import type { Metadata } from 'next';
import './globals.css';
import { AuthSessionProvider } from '@/lib/auth-session';

export const metadata: Metadata = {
  title: 'Aventi - Event Discovery SaaS',
  description: 'Aventi connects people with local events and gives operators visibility into market scans.',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body suppressHydrationWarning>
        <AuthSessionProvider>{children}</AuthSessionProvider>
      </body>
    </html>
  );
}
