import type { EventCard, EventCategory, EventVibeTag, SwipeAction } from '@aventi/contracts';

export type FeedMode = 'discover' | 'favorites' | 'admin';

export interface AdminMarket {
  key: string;
  city: string;
  tier: 'hot' | 'warm' | 'cold';
  status: 'ready' | 'warming' | 'targeted_warming' | 'no_matches';
  visibleEvents: number;
  lastRequested: string;
  lastScan: string;
  nextWindow: string;
  successRate: number;
}

export interface ScanRun {
  id: string;
  market: string;
  type: 'short_term' | 'long_term' | 'targeted';
  source: 'google-events' | 'serpapi' | 'manual';
  discovered: number;
  accepted: number;
  imageJobs: number;
  verificationJobs: number;
  status: 'succeeded' | 'running' | 'queued' | 'attention';
  startedAt: string;
}

export const heroImages = [
  'https://images.unsplash.com/photo-1514525253161-7a46d19cd819?auto=format&fit=crop&w=1600&q=85',
  'https://images.unsplash.com/photo-1505373877841-8d25f7d46678?auto=format&fit=crop&w=1600&q=85',
  'https://images.unsplash.com/photo-1492684223066-81342ee5ff30?auto=format&fit=crop&w=1600&q=85',
];

export const categoryLabels: Record<EventCategory, string> = {
  nightlife: 'Nightlife',
  dining: 'Dining',
  concerts: 'Live Music',
  wellness: 'Wellness',
  experiences: 'Arts',
  comedy: 'Comedy',
  sports: 'Sports',
  outdoors: 'Outdoors',
  markets: 'Markets',
  tech: 'Tech & Talks',
};

// The most-discovered sub-types within each parent category, drawn from event-app norms
// (Posh, Eventbrite, Luma, Resy, Meetup). Used to make filter chips more browseable.
export const categoryTopTags: Record<EventCategory, string[]> = {
  nightlife: ['Clubs', 'Rooftops', 'DJ Sets', 'Late-Night'],
  dining: ['Date Night', 'Tasting Menus', 'Brunch', 'Cocktail Bars'],
  concerts: ['Indie', 'Hip-Hop', 'Jazz', 'Acoustic'],
  wellness: ['Yoga', 'Run Clubs', 'Sound Baths', 'Movement'],
  experiences: ['Galleries', 'Workshops', 'Exhibits', 'Crafts'],
  comedy: ['Stand-Up', 'Improv', 'Drag Shows', 'Sketch'],
  sports: ['Pickup', 'Races', 'Climbing', 'Leagues'],
  outdoors: ['Hikes', 'Cycling', 'Paddling', 'Camping'],
  markets: ['Food Fests', 'Farmers', 'Makers', 'Pop-Ups'],
  tech: ['Meetups', 'Demos', 'Hackathons', 'Talks'],
};

export const vibeLabels: Record<EventVibeTag, string> = {
  chill: 'Chill',
  energetic: 'Energetic',
  intellectual: 'Smart',
  romantic: 'Date Night',
  social: 'Social',
  luxury: 'Elevated',
  'live-music': 'Live Music',
  wellness: 'Wellness',
  'late-night': 'Late Night',
  'solo-friendly': 'Solo-Friendly',
  family: 'Family',
  adventurous: 'Adventurous',
  intimate: 'Intimate',
  underground: 'Underground',
};

export const demoEvents: EventCard[] = [
  {
    id: 'evt-rooftop-orbit',
    title: 'Rooftop Orbit Sessions',
    description: 'A high-floor listening party with live percussion, open-air cocktails, and a skyline crowd.',
    category: 'nightlife',
    venueName: 'Canopy Hall',
    city: 'Denver',
    startsAt: '2026-04-29T02:00:00.000Z',
    endsAt: '2026-04-29T06:00:00.000Z',
    bookingUrl: 'https://example.com/rooftop-orbit',
    imageUrl: 'https://images.unsplash.com/photo-1514525253161-7a46d19cd819?auto=format&fit=crop&w=900&q=85',
    priceLabel: '$28',
    isFree: false,
    radiusMiles: 2.8,
    vibes: ['energetic', 'social', 'late-night'],
    tags: ['dj', 'rooftop', 'cocktails'],
    venueRating: 4.7,
    venueReviewCount: 842,
    ticketOffers: [{ url: 'https://example.com/rooftop-orbit', provider: 'Eventbrite', priceLabel: '$28' }],
  },
  {
    id: 'evt-studio-supper',
    title: 'Studio Supper Club',
    description: 'A chef-led dinner inside a ceramic studio, pairing seasonal plates with low-intervention wines.',
    category: 'dining',
    venueName: 'Kiln Table',
    city: 'Denver',
    startsAt: '2026-04-30T01:30:00.000Z',
    endsAt: '2026-04-30T04:00:00.000Z',
    bookingUrl: 'https://example.com/studio-supper',
    imageUrl: 'https://images.unsplash.com/photo-1414235077428-338989a2e8c0?auto=format&fit=crop&w=900&q=85',
    priceLabel: '$74',
    isFree: false,
    radiusMiles: 4.1,
    vibes: ['romantic', 'luxury', 'chill'],
    tags: ['dinner', 'wine', 'maker-space'],
    venueRating: 4.9,
    venueReviewCount: 318,
  },
  {
    id: 'evt-synth-garden',
    title: 'Synth Garden Picnic',
    description: 'Ambient modular sets in the conservatory with botanical mocktails and a soft landing zone.',
    category: 'concerts',
    venueName: 'Glasshouse Commons',
    city: 'Denver',
    startsAt: '2026-05-02T00:00:00.000Z',
    endsAt: '2026-05-02T03:00:00.000Z',
    bookingUrl: 'https://example.com/synth-garden',
    imageUrl: 'https://images.unsplash.com/photo-1506157786151-b8491531f063?auto=format&fit=crop&w=900&q=85',
    priceLabel: 'Free RSVP',
    isFree: true,
    radiusMiles: 6.5,
    vibes: ['chill', 'live-music', 'wellness'],
    tags: ['ambient', 'garden', 'picnic'],
    venueRating: 4.6,
    venueReviewCount: 127,
  },
  {
    id: 'evt-motion-lab',
    title: 'Motion Lab: New Moves',
    description: 'A beginner-friendly movement lab led by local dancers with a social wind-down after class.',
    category: 'wellness',
    venueName: 'Northline Studio',
    city: 'Denver',
    startsAt: '2026-05-03T17:00:00.000Z',
    endsAt: '2026-05-03T19:00:00.000Z',
    bookingUrl: 'https://example.com/motion-lab',
    imageUrl: 'https://images.unsplash.com/photo-1518611012118-696072aa579a?auto=format&fit=crop&w=900&q=85',
    priceLabel: '$18',
    isFree: false,
    radiusMiles: 3.3,
    vibes: ['wellness', 'social', 'energetic'],
    tags: ['movement', 'community', 'class'],
    venueRating: 4.8,
    venueReviewCount: 229,
  },
];

export const adminMarkets: AdminMarket[] = [
  {
    key: 'denver-co-us',
    city: 'Denver',
    tier: 'hot',
    status: 'ready',
    visibleEvents: 184,
    lastRequested: '6 min ago',
    lastScan: 'Today, 9:14 AM',
    nextWindow: 'Monday short_term',
    successRate: 0.94,
  },
  {
    key: 'boulder-co-us',
    city: 'Boulder',
    tier: 'warm',
    status: 'warming',
    visibleEvents: 37,
    lastRequested: '28 min ago',
    lastScan: 'Running now',
    nextWindow: 'long_term queued',
    successRate: 0.88,
  },
  {
    key: 'austin-tx-us',
    city: 'Austin',
    tier: 'hot',
    status: 'targeted_warming',
    visibleEvents: 212,
    lastRequested: '2 min ago',
    lastScan: 'Today, 9:01 AM',
    nextWindow: 'filtered scan active',
    successRate: 0.91,
  },
  {
    key: 'asheville-nc-us',
    city: 'Asheville',
    tier: 'cold',
    status: 'no_matches',
    visibleEvents: 5,
    lastRequested: '3 days ago',
    lastScan: 'Mon, 9:33 AM',
    nextWindow: 'cron re-arm',
    successRate: 0.73,
  },
];

export const scanRuns: ScanRun[] = [
  {
    id: 'run_9128',
    market: 'Denver',
    type: 'short_term',
    source: 'google-events',
    discovered: 96,
    accepted: 61,
    imageJobs: 18,
    verificationJobs: 61,
    status: 'succeeded',
    startedAt: '9:14 AM',
  },
  {
    id: 'run_9131',
    market: 'Boulder',
    type: 'long_term',
    source: 'serpapi',
    discovered: 41,
    accepted: 18,
    imageJobs: 9,
    verificationJobs: 18,
    status: 'running',
    startedAt: '9:22 AM',
  },
  {
    id: 'run_9134',
    market: 'Austin',
    type: 'targeted',
    source: 'google-events',
    discovered: 27,
    accepted: 12,
    imageJobs: 6,
    verificationJobs: 12,
    status: 'queued',
    startedAt: '9:28 AM',
  },
  {
    id: 'run_9116',
    market: 'Asheville',
    type: 'short_term',
    source: 'manual',
    discovered: 8,
    accepted: 3,
    imageJobs: 2,
    verificationJobs: 3,
    status: 'attention',
    startedAt: '8:48 AM',
  },
];

export function applySwipeAction(events: EventCard[], actions: Record<string, SwipeAction>, eventId: string, action: SwipeAction) {
  const nextActions = { ...actions, [eventId]: action };
  const nextEvents = action === 'pass' ? events.filter((event) => event.id !== eventId) : events;
  return { nextActions, nextEvents };
}
