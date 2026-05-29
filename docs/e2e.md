# E2E Workspaces

Aventi keeps end-to-end suites as first-class workspace packages:

- `apps/web-e2e` tests the Next app with Playwright.
- `apps/mobile-e2e` tests the Expo app with Maestro.
- `services/backend-e2e` tests the FastAPI backend over HTTP.

Useful commands:

```sh
pnpm e2e
pnpm e2e:web
pnpm e2e:mobile
pnpm e2e:backend
```

The web suite starts `@aventi/web` unless `AVENTI_WEB_E2E_START_SERVER=0`.
The backend suite targets `http://127.0.0.1:8000` by default and can start the API with `AVENTI_BACKEND_E2E_START_SERVER=1`.
