# DESIGN.md

## Purpose

This file defines the visual and UX rules for Aventi across web and mobile.
The current source of truth is the warm editorial Aventi mood board: deep forest identity, cream editorial space, mellow gold accents, clay warmth, candid city/social photography, and calm mobile product surfaces.

Aventi is an event discovery product. It helps people find experiences that match their vibe, including music, nightlife, dining, arts, culture, wellness, community events, and outdoor experiences.

This file is meant to guide both humans and AI agents. When making design decisions, prefer consistency, clarity, and emotional resonance over novelty.

---

## Brand Essence

Aventi should feel:

- curious
- social
- tasteful
- grounded
- energetic
- human
- premium but approachable
- warm
- editorial
- present

Aventi is not just an outdoor adventure brand.
Aventi is a broader discovery brand for people who want to find interesting things happening around them in cities and communities.

### Core brand values

- **Connected** — bring people together around shared interests and experiences
- **Bold** — invite people into new experiences with confidence
- **Mindful** — keep the experience calm, intentional, and not overwhelming
- **Explorative** — support curiosity across many categories and vibes
- **Flow** — make discovery feel smooth, intuitive, and rewarding

---

## Product Positioning

Aventi should feel like:

- a curated guide to what is worth doing
- an app for people with taste and curiosity
- a discovery tool that feels modern, warm, and culturally aware

Aventi should not feel like:

- a wilderness-only app
- a loud party flyer app
- a cluttered social network
- a sterile corporate dashboard
- a gamified chaos machine

---

## Design Principles

### 1. Curated over crowded
Show fewer, better things.
Avoid overwhelming the user with too many competing elements.

### 2. Calm confidence
Design should feel intentional, steady, and clean.
Avoid frantic, hyper-saturated, or noisy compositions.

### 3. Discovery with taste
Aventi should feel editorial, not generic.
Use strong imagery, good spacing, and clear hierarchy.

### 4. Human and social
Design should make experiences feel shared and real.
Favor candid, warm, lived-in moments over abstract tech visuals.

### 5. Mobile-first clarity
Every screen should have one obvious next action.
Layouts should prioritize scanning, swiping, and saving.

### 6. Consistency beats cleverness
Prefer extending the system over inventing one-off patterns.

---

## Audience

Primary audience includes people who enjoy discovering events and experiences of many kinds, especially in cities and active communities.

This includes interest in:

- live music
- food and drink
- nightlife
- arts and culture
- wellness
- community events
- local pop-ups
- seasonal experiences
- outdoor activities

The design should support a broad range of event types without feeling visually fragmented.

---

## Emotional Tone

Interfaces should evoke:

- anticipation
- curiosity
- belonging
- momentum
- warmth
- possibility

Avoid interfaces that evoke:

- pressure
- confusion
- visual fatigue
- emptiness
- artificial hype

---

## Visual Direction

### Overall aesthetic

Aventi should look:

- editorial
- cinematic
- modern
- spacious
- warm
- urban-curious
- softly premium
- grounded in real-life moments

### Moodboard cues

Use these cues across the marketing site, mobile app, and shared tokens:

- Deep green brand field with cream typography
- Cream / sand editorial sections with black-green text
- Mellow gold for small calls to action, dividers, logo accents, and “discover more” moments
- Clay orange-red as restrained warmth for nightlife, food, and alert accents
- Sage / moss neutrals for calm secondary surfaces
- Ocean blue-green only as a muted city-depth accent
- Candid photo collage feeling: neighborhood evenings, music, food, arts, outdoors, wellness, community
- Rounded but not bubbly controls
- Poppins typography with strong headlines and readable body text

### Imagery direction

Use imagery that feels:

- candid
- atmospheric
- socially alive
- grounded in real places
- emotionally inviting

Preferred image subjects:

- friends arriving somewhere interesting
- live music scenes
- rooftops and city evenings
- food and drink moments
- art spaces and markets
- wellness gatherings
- community events
- neighborhood discovery
- occasional outdoor escape

Nature can be present, but it must not dominate the visual identity.

### Avoid imagery that feels:

- overly corporate
- fake-stock and staged
- excessively wilderness-focused
- neon-club chaotic
- luxury-exclusive and cold
- too dark to read as welcoming

---

## Color System

Use semantic design tokens from the shared theme package.
Do not hardcode colors in app code.

### Color intent

The palette should balance:

- grounding
- energy
- sophistication
- warmth

### Primary roles

- **Forest `#032F25`**: core brand field, primary dark app canvas
- **Pine `#214437`**: raised dark surfaces, secondary brand depth
- **Sage `#9AAA8F`**: calm secondary accent, wellness/community support
- **Moss `#B8BA96`**: soft neutral-green bridge
- **Sand `#EDE3D1` / Cream `#F5F0E7`**: editorial page backgrounds and light surfaces
- **Mellow `#E3AD43`**: primary accent and CTA highlight
- **Clay `#B94A31`**: warm event energy, food/nightlife, caution
- **Ocean `#164A57`**: muted cool contrast and city-evening depth
- **Charcoal `#1F211F`**: dark text on light surfaces

### General color behavior

- Use dark green as an anchor, not as the only brand expression
- Keep high contrast for readability
- Use accent colors intentionally and sparingly
- Avoid rainbow-category overload
- Avoid harsh neon unless explicitly part of event imagery
- Avoid flat, lifeless grayscale UI

### Prohibited

- raw hex values in feature code
- arbitrary new accent colors
- low-contrast text on photography
- category color systems that feel childish or gamified

---

## Typography

Typography should feel:

- modern
- clean
- confident
- readable
- slightly editorial

### General rules

- Use the shared type scale and text styles only
- Maintain strong hierarchy
- Favor bold headlines with restrained supporting text
- Keep line lengths readable
- Avoid decorative type effects

### Preferred feel

- strong headline moments
- clean sans serif
- whitespace-supported hierarchy
- crisp labels and metadata

### Avoid

- multiple competing font families
- excessive letter spacing
- tiny metadata-heavy interfaces
- overly condensed or novelty display type
- gradient text
- outlined text
- drop shadows on text unless absolutely necessary for legibility on imagery

---

## Layout

### Layout philosophy

Aventi layouts should feel open, intentional, and easy to scan.

### Rules

- Prioritize vertical flow and mobile ergonomics
- One primary action per section
- Group related content clearly
- Use whitespace generously
- Keep card layouts breathable
- Make dense data feel lightweight through spacing and hierarchy

### Preferred composition

- clear hero area
- strong section titles
- modular cards
- deliberate rhythm between sections
- focused CTAs

### Avoid

- overpacked dashboards
- too many card styles on one screen
- nested containers that feel heavy
- long walls of equal-weight content
- unclear primary action

---

## Components

Use shared components from the design system whenever possible.
Do not reimplement common patterns inside feature folders unless necessary.

### Shared primitives should cover

- buttons
- text
- headings
- cards
- chips
- list items
- avatars
- tabs
- inputs
- sheets / modals
- empty states

### Component style rules

- rounded corners should feel soft, not bubbly
- borders should be subtle
- shadows should be minimal and tasteful
- cards should feel elevated through spacing first, effects second
- icons should support recognition, not dominate layouts

### Interaction feel

- smooth
- responsive
- polished
- calm

Microinteractions should reinforce confidence, not distract.

---

## Event Discovery UX Rules

### Discovery should feel:

- curated
- fast to scan
- easy to personalize
- rewarding to explore

### Event cards should usually communicate:

- image
- title
- category or vibe
- time/date
- location
- social proof or relevance when useful

### Filtering and personalization

Filters should feel lightweight, not like a spreadsheet.
Prefer vibe-based and category-based discovery over overly technical sorting.

### Saving and intent

Support lightweight intent:
- save
- maybe
- interested
- going

These actions should feel quick and low-friction.

### Avoid

- forms that interrupt discovery
- too many required decisions up front
- ranking logic that feels opaque or robotic
- over-explaining recommendations in the UI

---

## Platform Guidance

### Shared across web and mobile

The brand expression should feel consistent across platforms:
- same tokens
- same hierarchy logic
- same interaction philosophy
- same component family

### Acceptable platform differences

Web and mobile can differ in:
- navigation patterns
- gestures
- modal/sheet behavior
- input patterns
- spacing tuned for platform norms

Do not force exact visual parity when it harms usability.

### Shared package rules

Shared UI packages must remain platform-agnostic.
Do not import platform-specific routing or runtime APIs into shared design primitives.

---

## Accessibility

Accessibility is part of good design, not an afterthought.

### Requirements

- maintain readable contrast
- support dynamic text where applicable
- preserve clear focus states
- touch targets should be large enough
- do not rely on color alone for meaning
- ensure hierarchy is understandable without imagery

### Avoid

- tiny type
- low-contrast overlays on images
- ambiguous icon-only actions without labels or affordances
- gesture-only critical actions

---

## Motion

Motion should communicate:

- continuity
- responsiveness
- delight
- spatial understanding

### Good motion feels

- subtle
- smooth
- quick
- intentional

### Avoid motion that feels

- gimmicky
- bouncy for no reason
- slow and interruptive
- overused

Animation should support discovery, transitions, saving, and feedback — not compete with content.

---

## Copy and UI Tone

UI copy should sound:

- human
- clear
- confident
- welcoming
- lightly inspiring

### Good copy traits

- concise
- natural
- socially aware
- not overly salesy
- not robotic

### Avoid copy that is

- overly corporate
- excessively witty
- pushy
- vague
- generic startup fluff

Good Aventi copy should make users feel:
“There’s probably something interesting nearby, and this app helps me find it.”

---

## What Agents Must Do

When generating or editing UI:

1. Reuse shared tokens
2. Reuse shared components first
3. Preserve the Aventi tone and aesthetic
4. Prefer calm, editorial layouts over noisy ones
5. Support a broad event-discovery audience, not just outdoor users
6. Keep screens mobile-first and action-oriented
7. Make the primary action obvious
8. Maintain accessibility and readable contrast

---

## What Agents Must Not Do

Agents must not:

- hardcode new visual styles outside the design system
- introduce random colors, spacing, or radii
- make the brand feel wilderness-only
- make the UI feel like a nightclub flyer
- overload screens with content
- create inconsistent button or card variants in app code
- use novelty styling that weakens cohesion
- choose aesthetics that conflict with the brand’s calm-confidence balance

---

## Decision Heuristic

When unsure, choose the option that feels:

- more curated
- more readable
- more grounded
- more human
- more socially inviting
- more consistent with a premium discovery experience

If one option is louder and one option is clearer, choose clearer.

If one option is trendier and one option is more durable, choose more durable.

If one option looks like a generic event aggregator and one feels like a curated local guide, choose the curated local guide.

---

## Summary

Aventi is a discovery brand for real-world experiences.

The design system should express:
- curiosity
- connection
- flow
- taste
- calm energy

Every design decision should help users feel that there is something worth discovering, and that Aventi can help them find it.
