import type { AdminMarketSummary, AdminUserLocationPoint } from '@aventi/contracts';
import { glass, type } from '../ui/app-ui';

type LatLng = { lat: number; lng: number };

function geoBounds(points: LatLng[]): { minLat: number; maxLat: number; minLng: number; maxLng: number } {
  if (points.length === 0) {
    return { minLat: 30, maxLat: 31, minLng: -98, maxLng: -97 };
  }
  let minLat = points[0].lat;
  let maxLat = points[0].lat;
  let minLng = points[0].lng;
  let maxLng = points[0].lng;
  for (const p of points) {
    minLat = Math.min(minLat, p.lat);
    maxLat = Math.max(maxLat, p.lat);
    minLng = Math.min(minLng, p.lng);
    maxLng = Math.max(maxLng, p.lng);
  }
  const padLat = Math.max((maxLat - minLat) * 0.12, 0.08);
  const padLng = Math.max((maxLng - minLng) * 0.12, 0.08);
  return {
    minLat: minLat - padLat,
    maxLat: maxLat + padLat,
    minLng: minLng - padLng,
    maxLng: maxLng + padLng,
  };
}

function projectToPercent(lat: number, lng: number, b: ReturnType<typeof geoBounds>) {
  const latSpan = Math.max(b.maxLat - b.minLat, 1e-6);
  const lngSpan = Math.max(b.maxLng - b.minLng, 1e-6);
  const x = ((lng - b.minLng) / lngSpan) * 100;
  const y = (1 - (lat - b.minLat) / latSpan) * 100;
  return {
    left: `${Math.min(96, Math.max(4, x))}%`,
    top: `${Math.min(96, Math.max(4, y))}%`,
  };
}

export function AdminPeopleMap({
  users,
  markets,
}: {
  users: AdminUserLocationPoint[];
  markets: AdminMarketSummary[];
}) {
  const marketCenters: LatLng[] = markets
    .filter(
      (m) =>
        typeof m.centerLatitude === 'number' &&
        typeof m.centerLongitude === 'number' &&
        !Number.isNaN(m.centerLatitude) &&
        !Number.isNaN(m.centerLongitude),
    )
    .map((m) => ({ lat: m.centerLatitude as number, lng: m.centerLongitude as number }));
  const userPts: LatLng[] = users.map((u) => ({ lat: u.latitude, lng: u.longitude }));
  const bounds = geoBounds([...userPts, ...marketCenters]);

  return (
    <div className={`${glass.card} p-4 space-y-3`}>
      <div>
        <h3 className={type.h2}>Where people are (profile GPS)</h3>
        <p className={`${type.caption} text-[var(--color-app-text-muted)] mt-1 max-w-[720px]`}>
          Each dot is the last location synced from the mobile app to <code className="text-[0.75rem]">profiles</code>.
          Rings are indexed market centers from inventory when coordinates exist. Markets can also be created from
          catalog venue cities without any user dot nearby—that is why the two layers do not always line up.
        </p>
      </div>
      <div
        className="relative w-full min-h-[min(52vw,320px)] max-h-[420px] rounded-[var(--radius-card)] border border-[var(--color-app-border)] bg-[var(--color-app-bg-elev)] overflow-hidden"
        role="img"
        aria-label="Scatter map of user locations and market centers"
      >
        {users.length === 0 && marketCenters.length === 0 ? (
          <div className="absolute inset-0 grid place-items-center p-6 text-center">
            <p className={`${type.body} text-[var(--color-app-text-muted)]`}>
              No coordinates yet. Open the app with location on so profiles pick up latitude and longitude, or import
              markets from the catalog so centers can appear.
            </p>
          </div>
        ) : null}
        {users.map((u) => {
          const pos = projectToPercent(u.latitude, u.longitude, bounds);
          return (
            <span
              key={u.userId}
              title={u.city ? `${u.city}` : u.userId.slice(0, 8)}
              className="absolute w-2.5 h-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--color-violet-bright)] shadow-[0_0_12px_rgba(167,139,250,0.55)]"
              style={{ left: pos.left, top: pos.top }}
            />
          );
        })}
        {markets.map((m) => {
          if (
            typeof m.centerLatitude !== 'number' ||
            typeof m.centerLongitude !== 'number' ||
            Number.isNaN(m.centerLatitude) ||
            Number.isNaN(m.centerLongitude)
          ) {
            return null;
          }
          const pos = projectToPercent(m.centerLatitude, m.centerLongitude, bounds);
          return (
            <span
              key={`m-${m.marketKey}`}
              title={`${m.city} (${m.marketKey})`}
              className="absolute w-4 h-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-[var(--color-success-neon)] bg-transparent opacity-90"
              style={{ left: pos.left, top: pos.top }}
            />
          );
        })}
      </div>
      <div className={`flex flex-wrap gap-4 ${type.caption} text-[var(--color-app-text-muted)]`}>
        <span className="inline-flex items-center gap-2">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-[var(--color-violet-bright)]" /> User (profile)
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="inline-block w-3 h-3 rounded-full border-2 border-[var(--color-success-neon)]" /> Market
          center
        </span>
      </div>
    </div>
  );
}
