export const dynamic = 'force-dynamic';

export function GET() {
  const appId = process.env.AVENTI_IOS_ASSOCIATED_APP_ID;
  if (!appId || !/^[A-Z0-9]+\.[a-zA-Z0-9.-]+$/.test(appId)) {
    return new Response('Association not configured', { status: 503 });
  }
  return Response.json({ applinks: { apps: [], details: [{ appID: appId, paths: ['/auth/*'] }] } });
}
