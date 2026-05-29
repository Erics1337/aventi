# Aventi Backend E2E

This workspace package smoke tests the FastAPI service over HTTP.

Use an already-running backend:

```sh
AVENTI_BACKEND_E2E_BASE_URL=http://127.0.0.1:8000 pnpm e2e:backend
```

Or let the test start the backend:

```sh
AVENTI_BACKEND_E2E_START_SERVER=1 pnpm e2e:backend
```
