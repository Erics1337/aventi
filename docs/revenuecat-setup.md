# RevenueCat setup record

The owner confirmed monthly and annual subscriptions and delegated the initial pricing choice. The brief $29 one-time proposal was withdrawn before any lifetime billing implementation or product creation.

## Pricing decision

- Monthly: USD $7.99, auto-renewing, no introductory trial.
- Annual: USD $49.99, auto-renewing, no introductory trial.
- Both unlock the same `premium` entitlement. Annual is approximately 48% less than twelve monthly payments.
- These are initial US base prices, not a demonstrated optimum. Mobile must display localized prices returned by the store, never hardcoded amounts.

Adjacent references checked: [AllTrails Plus](https://www.alltrails.com/plans) advertises $35.99 annually; [Wanderlog's US App Store listing](https://apps.apple.com/us/app/wanderlog-travel-planner/id1476732439) includes $49.99 annual products. These are imperfect comparables, not evidence of Aventi's conversion rate or unit economics.

## External setup

- Existing RevenueCat project: `82d7aafd` (Aventi).
- Created entitlement: `premium`, display name `Aventi Premium`.
- Created Test Store subscriptions (no trial): `aventi_premium_monthly` at $7.99/month, and `aventi_premium_annual` at $49.99/year. Both are attached to `premium`. The `default` offering is the active default and contains the Monthly and Annual packages.
- Intended corresponding store product identifiers: `aventi_premium_monthly`, `aventi_premium_annual`.
- Transfer behavior: **Keep with original App User ID**, with the same behavior in sandbox.
- Sandbox entitlement access: **Allowed App User IDs only**. Add the permanent Aventi test-account UUIDs before purchase testing; none were invented or allowlisted during setup.
- Created V1 secret API key labeled `Aventi backend verification`, matching the backend's RevenueCat V1 subscriber API. Saved the key, generated webhook authorization secret, entitlement ID and product IDs in AWS Secrets Manager `aventi-dev/backend/env`; existing unrelated values were preserved. Both launch feature switches are explicitly false. No key values are stored in this document or Git.
- A webhook destination has not been enabled: the launch webhook route still needs a validated staging deployment. A secret alone is not a working integration.
- Connected the existing signed-in Chrome tab to both developer consoles; no new browser window is needed.
- Verified Apple app `6765957039` has bundle `com.aventi.app`. Created subscription group `22416877` (Aventi Premium), monthly product `6816561678` (`aventi_premium_monthly`) and annual product `6816562101` (`aventi_premium_annual`). Saved $7.99 monthly and $49.99 annual upfront prices, US-only availability, and English display names/descriptions; no introductory offers. Products remain unsubmitted and require review screenshots and final metadata. Apple initially assigned different service levels; align both at the same level before release.
- Created RevenueCat Apple app `appa2382a61aa`. Confirmed existing IAP key `386LCH87U9` and catalog key `35N6989DA5` belong to the same Apple issuer as Aventi (`32288ce1-d4f2-48e4-b052-06e68bb559ef`), then reused the keys already held by RevenueCat. Both display **Valid credentials**. RevenueCat confirmed App Store Server Notifications were updated in App Store Connect.
- Imported both Apple products, attached them to `premium`, and mapped them into the existing default Monthly/Annual offering packages alongside Test Store products.
- Verified Google Play app `4975367588364523451` uses package `com.crestcode.aventi` in developer account `7404641502830463153`. Play's subscriptions page requires uploading a billing-capable build before product creation. Created RevenueCat Google app `appff82c6f05c`; service-account credentials and developer notifications remain unconfigured.
- The owner accepted the updated Apple Developer Program License Agreement. App Store Connect Business now shows both the Free Apps and Paid Apps agreements as Active.
- Store setup remains separate from RevenueCat Test Store products. Test Store prices do not configure Apple or Google billing.
- Apple bundle and Google package in source match the verified store records.
- Saved the real iOS and Android public RevenueCat SDK keys to the Aventi Expo project's development, preview, and production environments. This does not enable purchases; backend switches remain false, and Android credentials still need configuration.
- Owner confirmed they do **not** own `aventi.app`. Removed that marketing URL from the Apple draft and verified the saved empty field. Do not use that domain for links, auth callbacks, or deployment. Owner authorized `crestcodecreative.com`, which is present in the signed-in Vercel team's domains. The proposed `aventi.crestcodecreative.com` subdomain has no DNS record yet. The owner confirmed `admin@crestcodecreative.com` for Aventi support.
- Changed the Apple draft to **Manually release this version**, verified saved, to preserve the separate public-rollout gate.
- Owner set a **$20/month combined provider spending ceiling**, replacing the unresolved daily-dollar budget question, and requested Pollinations. Paid processing stays disabled while the shared monetary ledger and provider cost bounds are validated. This does not authorize additional subscription commitments or automatic credit replenishment.
- Saved `AVENTI_PROVIDER_MONTHLY_BUDGET_MICROUSD=20000000` in the existing development AWS secret, preserving other entries and keeping paid processing disabled. This configuration is not a deployed budget ledger.
- Validated the existing Pollinations secret key through its read-only `/account/key` endpoint (HTTP 200, valid). No generation credits were spent. Premium insight selection now uses the authenticated Pollinations API with a pinned model, bounded input/output, and a strict allowlist of server-provided fact/event IDs. Image generation uses the current authenticated API, one request per reservation, and stores the result; it never exposes a generation URL as a fallback image.

## Provider pricing verification before enabling processing

The public [Pollinations model catalogue](https://github.com/pollinations/pollinations/blob/main/gen.pollinations.ai/src/docs/models.md) was checked on 2026-09-27 UTC. The selected text model `openai/gpt-5.4-nano` advertised 0.00000015 Pollen per input token and 0.0000009375 per completion token. `black-forest-labs/flux.1-schnell` advertised a flat 0.002 Pollen image rate. These are provider credits, not a guarantee of invoice cost; conversion, taxes, current model pricing, and a conservative maximum cost per call must be verified before paid processing is enabled. The monthly ledger is only a real spending bound when every configured reservation covers the entire bounded request cost. No automatic top-up was configured.

The owner selected the existing stock Vercel web origin `https://aventi-web.vercel.app` for Aventi's policies and support, without a custom domain. PR #14 adds direct privacy, terms, support, recovery, and external deletion-request routes plus a marketing-only homepage; its preview build and routes pass. Production remains on the older May deployment until GitHub's required approving review permits merge. The Apple draft still uses the temporary Crest-hosted URLs and must be changed to Aventi's own live URLs after production deployment. The Aventi Vercel Production policy URL variables have already been changed to the stock-domain paths, and the confirmed support email remains `admin@crestcodecreative.com`.

## Existing development infrastructure inspection

AWS, Supabase and Expo CLI authentication succeeded. The Aventi Supabase project is `mkwvqzgngiclybvklorr`; Expo project is `0a7b66a7-c65c-4356-a5da-5eccde6e5000`. Only `aventi-dev` Lambda services and its backend runtime secret were found in AWS us-east-1. No Expo environment variables were present in development, preview or production.

Applied only the domain-security section of migration `0010` to the existing development database: enabled RLS for public tables, revoked anonymous/authenticated table and sequence privileges, restricted default privileges, and removed the permissive image-upload policy. Verified zero public domain tables with missing RLS or direct client read/write grants. This does not mean all launch migrations are deployed.

The existing API `/v1/health` endpoint returned HTTP 200. A request to the wrong `/health` path initially returned 502; direct Lambda investigation observed an initialization timeout followed by a 404 for that wrong path. Staging deployment and startup performance validation remain required.

No public rollout, store submission, or paid provider processing was enabled.
