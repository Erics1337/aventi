export const dynamic = 'force-dynamic';

export function GET() {
  const packageName = process.env.AVENTI_ANDROID_PACKAGE;
  const fingerprints = process.env.AVENTI_ANDROID_SHA256_FINGERPRINTS?.split(',').map(value => value.trim());
  if (!packageName || !fingerprints?.length || fingerprints.some(value => !/^(?:[A-Fa-f0-9]{2}:){31}[A-Fa-f0-9]{2}$/.test(value))) {
    return new Response('Association not configured', { status: 503 });
  }
  return Response.json([{ relation: ['delegate_permission/common.handle_all_urls'], target: { namespace: 'android_app', package_name: packageName, sha256_cert_fingerprints: fingerprints } }]);
}
