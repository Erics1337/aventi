import { useEffect, useMemo, useRef, useState } from 'react';
import type { EventCard, EventVibeTag, SwipeAction, VibeWeightMap } from '@aventi/contracts';
import { RANKING_CONSTANTS } from '@aventi/contracts';

function scoreEvent(event: EventCard, weights: VibeWeightMap): number {
  return event.vibes.reduce((sum, vibe) => sum + (weights[vibe] ?? RANKING_CONSTANTS.BASELINE_WEIGHT), 0);
}

function applySwipeUpdate(current: VibeWeightMap, vibes: EventVibeTag[], action: SwipeAction): VibeWeightMap {
  const next = { ...current };
  for (const vibe of vibes) {
    const existing = next[vibe] ?? RANKING_CONSTANTS.BASELINE_WEIGHT;
    next[vibe] =
      action === 'like'
        ? existing * RANKING_CONSTANTS.LIKE_MULTIPLIER + RANKING_CONSTANTS.LIKE_BONUS
        : existing * RANKING_CONSTANTS.PASS_MULTIPLIER;
  }
  return next;
}

export function useEventFeed(initialEvents: EventCard[], resetKey?: string) {
  const [weights, setWeights] = useState<VibeWeightMap>({});
  const [history, setHistory] = useState<EventCard[]>([]);
  const [events, setEvents] = useState<EventCard[]>(initialEvents);
  const prevEventsRef = useRef<string>('');

  useEffect(() => {
    const serialized = JSON.stringify(initialEvents.map((e) => e.id));
    if (serialized !== prevEventsRef.current) {
      prevEventsRef.current = serialized;
      setEvents(initialEvents);
      setHistory([]);
    }
  }, [initialEvents, resetKey]);

  const rankedEvents = useMemo(() => {
    return [...events].sort((a, b) => scoreEvent(b, weights) - scoreEvent(a, weights));
  }, [events, weights]);

  const currentEvent = rankedEvents[0] ?? null;

  const swipe = (action: SwipeAction) => {
    if (!currentEvent) {
      return { remaining: 0 };
    }

    setWeights((prev) => applySwipeUpdate(prev, currentEvent.vibes, action));
    setHistory((prev) => [...prev, currentEvent]);
    setEvents((prev) => prev.filter((event) => event.id !== currentEvent.id));

    return { remaining: Math.max(0, rankedEvents.length - 1) };
  };

  return {
    currentEvent,
    queue: rankedEvents,
    history,
    weights,
    swipe,
    canReviewHistory: history.length > 0,
    setEvents,
    setHistory,
  };
}
