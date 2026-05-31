import type { Metadata } from 'next';
import { SavedPage } from '@/components/AventiWebApp';

export const metadata: Metadata = {
  title: 'Saved — Aventi',
  description: 'Review the events you saved in Aventi and jump back into discovery.',
};

export default function Saved() {
  return <SavedPage />;
}
