import type { Metadata } from 'next';
import { PolicyLayout, type PolicySection } from '@/components/legal/PolicyLayout';

export const metadata: Metadata = {
  title: 'Aventi Privacy Policy',
  description: 'How Aventi handles account, location, event preference, and purchase data.',
};

const sections: PolicySection[] = [
  { title: 'Information Aventi handles', paragraphs: [
    'When you use Aventi, we handle the information needed to provide event discovery: your account identifier and email if you create a permanent account; location coordinates or a destination you choose; discovery preferences and filters; likes, passes, saved events, and reports; and technical information needed to operate and secure the service, such as request logs and IP addresses.',
    'If you purchase Premium, Apple or Google processes your payment. Aventi and RevenueCat receive purchase identifiers and subscription status to determine access. We do not receive your full payment card number. If you contact support, we handle the message and contact details you provide.',
  ] },
  { title: 'How we use it', paragraphs: [
    'We use this information to authenticate your account, find and rank eligible events, remember your preferences and saved events, enforce free-use limits, provide Premium features, prevent abuse, respond to reports and support requests, and maintain service reliability. Device location is used for nearby discovery when you grant permission. You can instead choose a supported destination with Travel Mode when that feature is available to your account.',
    'Premium match explanations, insider tips, event pairings, and event imagery may be generated with AI. These features use event and venue information and relevant preference or filter inputs. Generated content is labeled in the app and may be unavailable when source information or provider capacity is insufficient.',
  ] },
  { title: 'Providers and event links', paragraphs: [
    'We use Supabase for accounts and application data, AWS for the API and background processing, RevenueCat for subscription status, Google services for destination lookup and time zones, and event discovery, verification, and AI providers such as SerpApi, Gemini, and Pollinations when those features are enabled. These providers receive only information needed for the relevant task. Event booking links lead to independent sites with their own privacy practices.',
  ] },
  { title: 'Your choices and deletion', paragraphs: [
    'You can decline device location permission, change your discovery settings, remove saved events, and request account deletion in the app. You can also use our external account-deletion page. Deletion removes the Aventi account and associated application records through a resumable process. A limited deletion request record may remain to prevent a deleted account from being recreated by an old session and to document completion. Records may also be retained where required for security, legal, or financial obligations.',
    'Deleting your Aventi account does not cancel a subscription billed by Apple or Google. Manage or cancel that subscription in the relevant app store. You can contact us to ask about your information or request help with deletion.',
  ] },
  { title: 'Security and changes', paragraphs: [
    'We use access controls and other safeguards designed to limit access to account data. No internet service can promise perfect security. We may update this policy as Aventi changes; the date on this page shows the latest version.',
  ] },
];

export default function PrivacyPage() {
  return <PolicyLayout title="Privacy Policy" intro="Aventi is an event discovery app operated by Crest Code Creative. This policy describes the information used to provide the app and your choices about it." sections={sections} />;
}
