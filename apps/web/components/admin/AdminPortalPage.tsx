'use client';
import { useEffect, useState } from 'react';
import { Activity, Gauge, Import, Loader2, Lock, Play, RefreshCcw, Users } from 'lucide-react';
import type { AdminDashboardResponse, AdminMarketSummary, AdminUserLocationPoint } from '@aventi/contracts';
import { createAventiApi } from '@/lib/api';
import { useAuthSession } from '@/lib/auth-session';
import { AuthModal } from '../AuthModal';
import { Button, Pill, Surface, glass, motion, type } from '../ui/app-ui';
import { AppShell } from '../ui/app-shell';
import { AdminPeopleMap } from './AdminPeopleMap';

function formatDateTime(value?: string | null) {
  if (!value) return 'Not recorded';
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value));
}

function marketStatus(market: AdminMarketSummary) {
  if (market.lastError) return 'attention';
  if (market.scanLockUntil && new Date(market.scanLockUntil).getTime() > Date.now()) return 'warming';
  if (market.lastTargetedRequestedAt && market.lastTargetedRequestedAt !== market.lastTargetedCompletedAt) {
    return 'targeted_warming';
  }
  return 'ready';
}

export function AdminPortalPage() {
  const auth = useAuthSession();
  const [activeTab, setActiveTab] = useState<'people' | 'markets' | 'scans'>('people');
  const [dashboard, setDashboard] = useState<AdminDashboardResponse | null>(null);
  const [userLocations, setUserLocations] = useState<AdminUserLocationPoint[] | null>(null);
  const [peopleLoading, setPeopleLoading] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [syncBusy, setSyncBusy] = useState(false);
  const [scanBusyKey, setScanBusyKey] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadDashboard(token?: string | null) {
    const t = token ?? auth.session?.access_token ?? null;
    if (!t) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await createAventiApi(t).getAdminDashboard();
      setDashboard(data);
    } catch (err) {
      setDashboard(null);
      setError(err instanceof Error ? err.message : 'Unable to load admin dashboard');
    } finally {
      setIsLoading(false);
    }
  }

  async function importMarketsFromCatalog() {
    const t = auth.session?.access_token ?? null;
    if (!t) return;
    setSyncBusy(true);
    setError(null);
    setActionError(null);
    try {
      await createAventiApi(t).postAdminImportMarketsFromCatalog();
      await loadDashboard(t);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to import markets from catalog');
    } finally {
      setSyncBusy(false);
    }
  }

  async function loadPeopleLocations() {
    const t = auth.session?.access_token ?? null;
    if (!t) return;
    setPeopleLoading(true);
    try {
      const res = await createAventiApi(t).getAdminUserLocations();
      setUserLocations(res.users);
    } catch {
      setUserLocations([]);
    } finally {
      setPeopleLoading(false);
    }
  }

  async function enqueueMarketScan(marketKey: string) {
    const t = auth.session?.access_token ?? null;
    if (!t) return;
    setScanBusyKey(marketKey);
    setActionError(null);
    try {
      await createAventiApi(t).postAdminEnqueueMarketScan({ marketKey });
      await loadDashboard(t);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Unable to enqueue market scan');
    } finally {
      setScanBusyKey(null);
    }
  }

  useEffect(() => {
    if (auth.isReady && auth.session) {
      void loadDashboard(auth.session.access_token);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth.isReady]);

  useEffect(() => {
    if (activeTab !== 'people' || !auth.isReady || !auth.session?.access_token) return;
    void loadPeopleLocations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, auth.isReady, auth.session?.access_token]);

  const tabBtn = (tab: 'people' | 'markets' | 'scans') =>
    `${motion.base} inline-flex items-center gap-2 h-9 px-3.5 rounded-full text-[0.8125rem] font-semibold ${
      activeTab === tab
        ? 'bg-[var(--color-violet)] text-white shadow-[var(--glow-violet)]'
        : 'bg-transparent text-[var(--color-app-text-muted)] hover:text-[var(--color-app-text)]'
    }`;

  const statusPill = (status: string) => {
    const tone =
      status === 'ready'
        ? 'bg-[rgba(77,255,168,0.10)] text-[var(--color-success-neon)] border-[var(--color-success-neon)]/40'
        : status === 'warming' || status === 'targeted_warming' || status === 'running' || status === 'queued' || status === 'completed'
        ? 'bg-[rgba(47,143,104,0.14)] text-[var(--color-violet-bright)] border-[var(--color-violet)]/40'
        : status === 'succeeded'
        ? 'bg-[rgba(77,255,168,0.10)] text-[var(--color-success-neon)] border-[var(--color-success-neon)]/40'
        : 'bg-[var(--color-app-surface)] text-[var(--color-app-text-muted)] border-[var(--color-app-border)]';
    return `inline-flex items-center px-2.5 h-6 rounded-full text-[0.7rem] font-semibold border ${tone}`;
  };

  return (
    <AppShell active="admin">
      <section
        className="scrollbar-none flex min-h-0 flex-1 flex-col overflow-y-auto px-4 sm:px-6 md:px-8 pt-6 md:pt-8 pb-12 max-w-[1100px] mx-auto w-full"
        id="admin"
      >
        <div className="max-w-[720px] mb-8">
          <Pill tone="violet">Admin portal</Pill>
          <h1 className={`${type.display} mt-3 mb-3`}>
            Backend market scans, visible at a glance.
          </h1>
          <p className={`${type.body} text-[var(--color-app-text-muted)] max-w-[560px]`}>
            Operational views for heat tiers, inventory status, worker activity, ingest performance,
            and verification queues — kept calm, not noisy.
          </p>
        </div>

        <Surface elev className="p-5">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
            <div>
              <span className={`${type.label} text-[var(--color-app-text-muted)]`}>Operations</span>
              <h2 className={`${type.h1} mt-1`}>Chron market scan console</h2>
            </div>
            <div className="flex flex-wrap items-center gap-2 justify-end">
              <div
                className="flex items-center gap-1 p-1 rounded-full border border-[var(--color-app-border)] bg-[var(--color-app-surface)]"
                role="tablist"
                aria-label="Admin views"
              >
                <button className={tabBtn('people')} type="button" onClick={() => setActiveTab('people')}>
                  <Users size={14} strokeWidth={1.6} />
                  People
                </button>
                <button className={tabBtn('markets')} type="button" onClick={() => setActiveTab('markets')}>
                  <Gauge size={14} strokeWidth={1.6} />
                  Markets
                </button>
                <button className={tabBtn('scans')} type="button" onClick={() => setActiveTab('scans')}>
                  <Activity size={14} strokeWidth={1.6} />
                  Scans
                </button>
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void importMarketsFromCatalog()}
                disabled={isLoading || syncBusy}
                title="Upsert market_inventory_state from venue cities on your event catalog (wide occurrence window), then recompute visible 7-day counts and heat tiers."
                leadingIcon={<Import size={14} strokeWidth={1.6} />}
              >
                Import catalog markets
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => loadDashboard()}
                disabled={isLoading || syncBusy}
                leadingIcon={<RefreshCcw size={14} strokeWidth={1.6} />}
              >
                Refresh
              </Button>
            </div>
          </div>

          {actionError ? (
            <p className={`${type.body} text-[var(--color-danger-glow)] mb-4`} role="alert">
              {actionError}
            </p>
          ) : null}

          {error ? (
            <Surface className="grid gap-3 place-items-center p-8 text-center mb-5">
              <Lock size={24} className="text-[var(--color-danger-glow)]" />
              <h3 className={type.h1}>Admin access blocked</h3>
              <p className={`${type.body} text-[var(--color-app-text-muted)] max-w-[560px]`}>
                {error.includes('403')
                  ? 'This Supabase user is signed in, but the backend rejected the admin role claim.'
                  : error}
              </p>
            </Surface>
          ) : null}

          {isLoading && !dashboard ? (
            <Surface className="grid gap-3 place-items-center p-8 text-center mb-5">
              <Loader2 size={24} className="animate-spin text-[var(--color-violet-bright)]" />
              <h3 className={type.h1}>Loading scan telemetry</h3>
              <p className={`${type.body} text-[var(--color-app-text-muted)] max-w-[560px]`}>
                Reading market inventory state, ingest runs, and verification health from the backend.
              </p>
            </Surface>
          ) : dashboard ? (
            <>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
                {[
                  { label: 'Markets', value: dashboard.rollup.marketsTotal },
                  { label: 'Hot markets', value: dashboard.rollup.hotMarkets },
                  { label: 'Active scans', value: dashboard.rollup.activeScans },
                  { label: 'Verification backlog', value: dashboard.rollup.verificationBacklog },
                ].map((metric) => (
                  <div
                    key={metric.label}
                    className={`${glass.card} p-4`}
                  >
                    <span className={`${type.label} text-[var(--color-app-text-muted)]`}>
                      {metric.label}
                    </span>
                    <strong className="block mt-2 text-[2rem] leading-none font-extrabold tracking-[-0.01em]">
                      {metric.value}
                    </strong>
                  </div>
                ))}
              </div>

              {activeTab === 'people' ? (
                peopleLoading ? (
                  <Surface className="grid gap-3 place-items-center p-8 text-center mb-5">
                    <Loader2 size={24} className="animate-spin text-[var(--color-violet-bright)]" />
                    <p className={`${type.body} text-[var(--color-app-text-muted)]`}>Loading profile locations…</p>
                  </Surface>
                ) : (
                  <AdminPeopleMap users={userLocations ?? []} markets={dashboard.markets} />
                )
              ) : null}

              {activeTab === 'markets' && dashboard.markets.length === 0 ? (
                <p
                  className={`${type.body} text-[var(--color-app-text-muted)] mb-5 max-w-[560px]`}
                >
                  No markets are indexed yet. Rows are usually created when the mobile app reports
                  activity or a scan runs. If you already have events in Postgres, use{' '}
                  <strong className="text-[var(--color-app-text)]">Import catalog markets</strong> above
                  to backfill one row per venue city from the catalog.
                </p>
              ) : null}

              {activeTab === 'markets' ? (
                <>
                  {/* Desktop table — hidden on mobile */}
                  <div className={`${glass.card} overflow-x-auto hidden md:block`} role="table" aria-label="Market inventory state">
                    <div
                      className={`grid grid-cols-[1.25fr_0.95fr_0.55fr_0.95fr_0.95fr_0.55fr_auto] gap-3 min-w-[940px] px-4 py-3 items-center ${type.label} text-[var(--color-app-text-muted)]`}
                      role="row"
                    >
                      <span>Market</span>
                      <span>Status</span>
                      <span>Visible</span>
                      <span>Last scan</span>
                      <span>Targeted</span>
                      <span>Users</span>
                      <span className="text-right">Scan</span>
                    </div>
                    {dashboard.markets.map((market) => {
                      const status = marketStatus(market);
                      const queueOk = dashboard.workerQueue.configured;
                      return (
                        <div
                          className={`grid grid-cols-[1.25fr_0.95fr_0.55fr_0.95fr_0.95fr_0.55fr_auto] gap-3 min-w-[940px] px-4 py-3 items-center border-t border-[var(--color-app-border)] ${type.body}`}
                          role="row"
                          key={market.marketKey}
                        >
                          <span>
                            <strong className="block text-[var(--color-app-text)]">{market.city}</strong>
                            <small className={`block mt-1 ${type.caption}`}>
                              {market.heatTier} · {market.state ?? market.country}
                            </small>
                          </span>
                          <span className={statusPill(status)}>{status.replace('_', ' ')}</span>
                          <span>{market.visibleEventCount7d}</span>
                          <span>{formatDateTime(market.lastScanCompletedAt ?? market.lastScanStartedAt)}</span>
                          <span>{formatDateTime(market.lastTargetedRequestedAt)}</span>
                          <span>{market.activeUserCount7d}</span>
                          <span className="flex justify-end">
                            <Button
                              variant="secondary"
                              size="sm"
                              type="button"
                              disabled={!queueOk || scanBusyKey === market.marketKey}
                              title={
                                queueOk
                                  ? 'Queue one short-window SerpAPI MARKET_SCAN for this city (requires worker + SQS).'
                                  : 'Configure SQS_WORKER_QUEUE_URL so jobs can be enqueued.'
                              }
                              leadingIcon={<Play size={12} strokeWidth={1.6} />}
                              onClick={() => void enqueueMarketScan(market.marketKey)}
                            >
                              {scanBusyKey === market.marketKey ? '…' : 'Queue'}
                            </Button>
                          </span>
                        </div>
                      );
                    })}
                  </div>

                  {/* Mobile cards — visible below md */}
                  <div className="grid gap-3 md:hidden">
                    {dashboard.markets.map((market) => {
                      const status = marketStatus(market);
                      const queueOk = dashboard.workerQueue.configured;
                      return (
                        <article key={market.marketKey} className={`${glass.card} p-4 space-y-2`}>
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <strong className="block text-[var(--color-app-text)]">{market.city}</strong>
                              <small className={type.caption}>{market.heatTier} · {market.state ?? market.country}</small>
                            </div>
                            <span className={statusPill(status)}>{status.replace('_', ' ')}</span>
                          </div>
                          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[0.8rem]">
                            <span className="text-[var(--color-app-text-muted)]">Visible</span>
                            <span>{market.visibleEventCount7d}</span>
                            <span className="text-[var(--color-app-text-muted)]">Last scan</span>
                            <span>{formatDateTime(market.lastScanCompletedAt ?? market.lastScanStartedAt)}</span>
                            <span className="text-[var(--color-app-text-muted)]">Targeted</span>
                            <span>{formatDateTime(market.lastTargetedRequestedAt)}</span>
                            <span className="text-[var(--color-app-text-muted)]">Active users</span>
                            <span>{market.activeUserCount7d}</span>
                          </div>
                          <Button
                            variant="secondary"
                            size="sm"
                            type="button"
                            className="w-full mt-1"
                            disabled={!queueOk || scanBusyKey === market.marketKey}
                            title={
                              queueOk
                                ? 'Queue one short-window SerpAPI MARKET_SCAN for this city.'
                                : 'Configure SQS_WORKER_QUEUE_URL so jobs can be enqueued.'
                            }
                            leadingIcon={<Play size={12} strokeWidth={1.6} />}
                            onClick={() => void enqueueMarketScan(market.marketKey)}
                          >
                            {scanBusyKey === market.marketKey ? 'Queueing…' : 'Queue short scan'}
                          </Button>
                        </article>
                      );
                    })}
                  </div>
                </>
              ) : (
                <div className="grid gap-3">
                  {dashboard.ingestRuns.map((run) => (
                    <article
                      className={`${glass.card} grid grid-cols-1 sm:grid-cols-[minmax(220px,1fr)_minmax(280px,1.3fr)_auto] gap-4 items-center p-4`}
                      key={run.id}
                    >
                      <div>
                        <span className={`${type.label} text-[var(--color-violet-bright)]`}>
                          {run.id.slice(0, 12)}
                        </span>
                        <h4 className={`${type.h2} my-1`}>
                          {run.city ?? 'Unknown market'} · {run.sourceType ?? 'source'}
                        </h4>
                        <p className={type.caption}>
                          {run.sourceName ?? 'ingest'} started {formatDateTime(run.startedAt)}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {[
                          `${run.discoveredCount} found`,
                          `${run.insertedCount} inserted`,
                          formatDateTime(run.finishedAt),
                          run.errorMessage ? 'error' : 'clean',
                        ].map((s) => (
                          <span
                            key={s}
                            className="rounded-full px-2.5 h-6 inline-flex items-center bg-[var(--color-app-surface)] border border-[var(--color-app-border)] text-[0.7rem] font-medium text-[var(--color-app-text-muted)]"
                          >
                            {s}
                          </span>
                        ))}
                      </div>
                      <strong className={statusPill(run.status)}>{run.status}</strong>
                    </article>
                  ))}
                  <article
                    className={`${glass.card} grid grid-cols-1 sm:grid-cols-[minmax(220px,1fr)_minmax(280px,1.3fr)_auto] gap-4 items-center p-4`}
                  >
                    <div>
                      <span className={`${type.label} text-[var(--color-violet-bright)]`}>
                        verification
                      </span>
                      <h4 className={`${type.h2} my-1`}>Verification health</h4>
                      <p className={type.caption}>
                        {dashboard.workerQueue.configured
                          ? 'Worker queue configured'
                          : 'Worker queue not configured'}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {dashboard.verification.slice(0, 4).map((item) => (
                        <span
                          key={`${item.status}-${String(item.active)}`}
                          className="rounded-full px-2.5 h-6 inline-flex items-center bg-[var(--color-app-surface)] border border-[var(--color-app-border)] text-[0.7rem] font-medium text-[var(--color-app-text-muted)]"
                        >
                          {item.status}: {item.count}
                        </span>
                      ))}
                    </div>
                    <strong className={statusPill('ready')}>
                      {dashboard.workerQueue.pollSeconds}s poll
                    </strong>
                  </article>
                </div>
              )}
            </>
          ) : null}
        </Surface>
      </section>
      <AuthModal />
    </AppShell>
  );
}
