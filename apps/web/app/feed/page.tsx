import { Suspense } from 'react';
import { EventFeedPage } from '@/components/AventiWebApp';

export default function Feed() {
  // EventFeedPage uses useSearchParams() to react to ?filters=open. Next.js
  // requires it to be wrapped in <Suspense> at the route boundary, otherwise
  // static generation bails. fallback={null} renders nothing during the
  // sync-render bailout — the client mounts immediately after.
  return (
    <Suspense fallback={null}>
      <EventFeedPage />
    </Suspense>
  );
}
