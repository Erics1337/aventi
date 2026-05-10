import type { Metadata } from 'next';
import { ProfilePage } from '@/components/AventiWebApp';

export const metadata: Metadata = {
  title: 'Profile — Aventi',
  description: 'Manage your Aventi identity, access level, and account actions.',
};

export default function Profile() {
  return <ProfilePage />;
}
