const { spawn } = require('node:child_process');

const EXPO_URL_PATTERN = /(?:Waiting on|Metro waiting on)\s+(exp:\/\/\S+)/;
const MAX_OPEN_ATTEMPTS = 12;
const OPEN_RETRY_MS = 2500;

let expoUrl = null;
let openAttemptStarted = false;

function log(message) {
  process.stdout.write(`@aventi/mobile:dev-helper: ${message}\n`);
}

function spawnCommand(command, args, options = {}) {
  return spawn(command, args, {
    stdio: 'ignore',
    ...options,
  });
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function tryOpenSimulator(url) {
  if (openAttemptStarted) {
    return;
  }
  openAttemptStarted = true;

  spawnCommand('open', ['-a', 'Simulator']);
  log('Opening iOS Simulator');

  for (let attempt = 1; attempt <= MAX_OPEN_ATTEMPTS; attempt += 1) {
    await delay(OPEN_RETRY_MS);
    const openUrl = spawn('xcrun', ['simctl', 'openurl', 'booted', url], {
      stdio: 'ignore',
    });
    const code = await new Promise((resolve) => {
      openUrl.once('exit', resolve);
      openUrl.once('error', () => resolve(1));
    });
    if (code === 0) {
      log(`Opened Expo URL in simulator on attempt ${attempt}`);
      return;
    }
  }

  log('Unable to auto-open Expo URL in the simulator; Expo will keep running.');
}

function mirrorStream(stream, writer) {
  stream.on('data', (chunk) => {
    const text = chunk.toString();
    writer.write(text);
    if (expoUrl) {
      return;
    }
    const match = text.match(EXPO_URL_PATTERN);
    if (!match) {
      return;
    }
    expoUrl = match[1];
    void tryOpenSimulator(expoUrl);
  });
}

const expo = spawn('expo', ['start', '--clear'], {
  stdio: ['inherit', 'pipe', 'pipe'],
  env: process.env,
});

mirrorStream(expo.stdout, process.stdout);
mirrorStream(expo.stderr, process.stderr);

expo.on('exit', (code, signal) => {
  if (signal) {
    process.exit(0);
    return;
  }
  process.exit(code ?? 0);
});

expo.on('error', (error) => {
  process.stderr.write(`${String(error)}\n`);
  process.exit(1);
});

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    if (!expo.killed) {
      expo.kill(signal);
      return;
    }
    process.exit(0);
  });
}
