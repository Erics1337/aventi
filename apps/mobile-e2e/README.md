# Aventi Mobile E2E

This workspace package contains Maestro flows for the Expo app.

Run a local build or development client first, then run one of:

```sh
pnpm e2e:mobile
pnpm --filter @aventi/mobile-e2e e2e:ios
pnpm --filter @aventi/mobile-e2e e2e:android
```

Set `APP_ID` when targeting a different build flavor.
