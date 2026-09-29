import type { Metadata } from 'next';
import { PolicyLayout, type PolicySection } from '@/components/legal/PolicyLayout';

export const metadata: Metadata = {
  title: 'Aventi Terms of Service',
  description: 'Terms for using the Aventi event discovery mobile app.',
};

const sections: PolicySection[] = [
  { title: 'Using Aventi', paragraphs: ['Aventi helps you discover and save events. You are responsible for using the app lawfully, keeping a permanent account secure, and providing accurate information when you contact support or report an event. Do not interfere with the service, misuse other accounts, or attempt to evade use limits.'] },
  { title: 'Event information and booking', paragraphs: ['Event details come from third-party sources and can change, be cancelled, or contain errors. Verify the date, location, admission rules, availability, and price with the organizer before traveling or buying a ticket. A booking link takes you to an independent provider; Aventi does not sell event tickets or control that provider’s terms or refunds.'] },
  { title: 'Premium subscriptions', paragraphs: ['Premium offers unlimited preference actions, adjustable discovery radius, supported admission filters, travel planning, and eligible event insights while your subscription is active. Monthly and annual subscriptions renew automatically unless cancelled through Apple or Google. The app store shows the applicable local price and billing period before purchase. There is no introductory trial. The store handles payment, cancellation, and refunds under its rules. Cancelling normally preserves access through the paid period, subject to the store’s subscription status. Deleting an Aventi account does not cancel store billing; cancel it separately in your Apple or Google subscription settings.'] },
  { title: 'Availability and generated content', paragraphs: ['Event coverage varies by location and verified inventory. Search, maps, AI content, and other provider-backed features may be unavailable or delayed. AI-generated explanations, tips, imagery, and pairings are informational and can be incomplete or inaccurate; check source links and organizer information before acting on them. We may change or suspend features to maintain safety, reliability, or spending limits.'] },
  { title: 'Accounts and changes', paragraphs: ['You can request account deletion in the app or through our external deletion page. We may update these terms as Aventi changes. Continued use after updated terms take effect means you accept the updated terms, where permitted by applicable law.'] },
];

export default function TermsPage() {
  return <PolicyLayout title="Terms of Service" intro="By using Aventi, you agree to these terms." sections={sections} />;
}
