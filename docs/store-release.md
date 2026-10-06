# Store handoff draft

This is submission preparation, not approved policy text or a submitted listing.
Owner-provided signing identities, listing URLs, product pricing, support contacts,
review credentials and disclosures must be completed before signed store builds.

## Listing copy

**Name:** Aventi

**Short description:** Find events near you and save the plans you want to make.

**Description draft:**
Discover upcoming events across the United States, with availability depending on
verified local inventory. Explore by date, category and vibe, save favorites, and
open the source listing for booking details.

Free accounts include ten preference actions each UTC day and discovery within ten
miles. Premium adds unlimited preference actions, adjustable distance, source-backed
admission filters, US travel destinations, and AI-generated event insights when
supporting information is available. Plan trips up to sixty days ahead with date
ranges of up to seven days.

Monthly and annual subscriptions are offered through your device's store. Localized
prices appear before purchase. There is no introductory trial. Subscriptions renew
until cancelled through Apple or Google; deleting the Aventi account does not cancel
store billing.

## Reviewer journey

1. Supply a permanent reviewer account through each store's private review fields.
   Never commit its credentials. Include the configured sandbox product identifiers.
2. Open the app, continue as guest, permit location, browse and like an event. If
   permission is denied, describe the location-required screen; premium accounts can
   select a US destination using search.
3. Convert the guest account or sign in with the supplied account. Confirm email and
   verify a recovery email opens the installed app's password-reset flow.
4. On Profile, select the monthly or annual plan using the displayed store price.
   Exercise cancellation, pending approval, successful purchase and Restore Premium.
   Premium is activated after server reconciliation, not from the device response.
5. Search a US destination, select dates and admission filters, and open an event's
   AI-generated insights. Pending/unavailable content is an expected truthful state
   when source data or provider capacity is unavailable.
6. Save, remove, report, sign out and sign back in. Verify the previous account's
   pending actions and private caches do not appear in another account.
7. Use Manage subscription to open the store. Request account deletion separately.
   Partial deletion failures retry durably; deletion blocks ordinary API access.

## Required assets and disclosures

Capture screenshots from real, configured iOS and Android store builds. Include
actual populated discovery, event details, saved events, travel search and purchase
screens. Do not use illustrative marketing events as live-inventory evidence.
Provide app icon/store feature graphics in each console's required dimensions.

Prepare the privacy/data-safety answers from verified runtime behavior: Supabase
account/email data, device location, preferences, favorites/actions, reports, and
purchase identity/subscription state. Confirm RevenueCat and every provider's data
processing settings and the actual shipped SDK set before approving disclosures.
This checklist is not a substitute for owner-approved privacy and terms documents.

Use TestFlight and Play internal testing with isolated staging. Run the complete
acceptance record in [launch-readiness.md](launch-readiness.md), including physical
devices, accessibility, 100-event quality audit, load, backup restore and rollback.
Only then prepare signed production builds with `eas build --profile production`
for each platform. Store submission and rollout require a separate release action.
