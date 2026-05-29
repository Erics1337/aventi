import { spawn } from 'node:child_process';

const baseURL = process.env.AVENTI_BACKEND_E2E_BASE_URL ?? 'http://127.0.0.1:8000';
const shouldStartServer = process.env.AVENTI_BACKEND_E2E_START_SERVER === '1';
const DEFAULT_TIMEOUT_MS = 30_000;
let timeoutMs = DEFAULT_TIMEOUT_MS;
const rawTimeoutMs = process.env.AVENTI_BACKEND_E2E_TIMEOUT_MS;
if (rawTimeoutMs != null && rawTimeoutMs !== '') {
  const parsedTimeoutMs = Number(rawTimeoutMs);
  if (Number.isFinite(parsedTimeoutMs) && parsedTimeoutMs > 0) {
    timeoutMs = parsedTimeoutMs;
  } else {
    console.warn(
      `Invalid AVENTI_BACKEND_E2E_TIMEOUT_MS="${rawTimeoutMs}", falling back to ${DEFAULT_TIMEOUT_MS}`,
    );
  }
}

let server;

async function sleep(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchJson(path) {
  const response = await fetch(new URL(path, baseURL));
  const body = await response.text();
  let json;

  try {
    json = JSON.parse(body);
  } catch {
    json = body;
  }

  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}: ${body}`);
  }

  return json;
}

async function waitForHealth() {
  const startedAt = Date.now();
  let lastError;

  while (Date.now() - startedAt < timeoutMs) {
    try {
      return await fetchJson('/v1/health');
    } catch (error) {
      lastError = error;
      await sleep(500);
    }
  }

  throw lastError ?? new Error(`Timed out waiting for ${baseURL}/v1/health`);
}

if (shouldStartServer) {
  server = spawn(
    'uv',
    ['run', '--project', '../backend', 'python', '-m', 'aventi_backend.main'],
    {
      cwd: new URL('..', import.meta.url),
      stdio: 'inherit',
      env: {
        ...process.env,
        AVENTI_ENV: process.env.AVENTI_ENV ?? 'test',
        AVENTI_AUTH_DEV_BYPASS: process.env.AVENTI_AUTH_DEV_BYPASS ?? 'true',
      },
    },
  );
}

try {
  const health = await waitForHealth();

  if (health.status !== 'ok' || health.service !== 'aventi-api') {
    throw new Error(`Unexpected health payload: ${JSON.stringify(health)}`);
  }

  console.log(`Backend health ok at ${baseURL}`);
} finally {
  server?.kill('SIGTERM');
}
