# Changelog


## 1.2.0 — Universal Steam game selection

- Added Steam Store game search and manual AppID / Store URL selection.
- Generalized Steam achievement schema and player progress retrieval to use the selected AppID.
- Made the game title, AppID and achievement totals dynamic in the OBS overlay.
- Added a persistent, per-game six-hour achievement schema cache.
- Queued every newly detected achievement so multiple unlocks between polls each trigger a notification.
- Reset notification baselines when switching accounts or games.
- Preserved compatibility with the original v1.1 configuration format by migrating its previously hard-coded game selection.
- Added GitHub Actions tests for Python 3.10–3.14, using current major versions of the official setup actions.
- Added SECURITY.md and updated the README, compatibility notes and Git ignore rules.
- Fixed release documentation wording and included the MIT License in the release package.

Compatibility is limited to Steam games that expose achievement schemas and player achievement data through Steamworks.

## 1.3.0 — Backend refactor and focused game search

- Split backend responsibilities into configuration, Steam client, achievement service, HTTP server and application modules.
- Kept `server.py` as a small launcher entry point for existing startup scripts.
- Limited Steam Store game search results to a maximum of three in both backend responses and the setup UI.
- Updated project wording and examples to describe the tool as a Steam-wide achievement overlay rather than a single-game utility.
- Kept the legacy v1.1 configuration migration for existing users.
- Expanded tests for module boundaries, game search limits, configuration migration, multi-unlock notifications and local HTTP protections.

## 1.4.0 — Readable overlay, pinned objectives and full-game search

- Increased achievement card sizes, icon dimensions, headings and description text for better stream readability.
- Added a dedicated Pinned view for up to three achievements, with pins saved locally per Steam account and game.
- Preserved the complete achievement list and the All / Unlocked / Locked filters.
- Changed Steam Store search to verify candidate items through AppDetails and return full games only; DLC, demos, soundtracks, software and unknown item types are excluded.
- Updated the project disclaimer to refer to rights holders collectively rather than naming individual publishers.
- Updated OBS Browser Source recommended dimensions to 560 × 900.

## 1.5.0 — Separate OBS widget and achievement dashboard

- Replaced the full achievement browser in the OBS source with a focused game title, completion count, percentage and progress bar.
- Kept up to three optional pinned achievement cards beneath the compact progress summary.
- Added a separate `/dashboard` page for the complete achievement library, All / Unlocked / Locked filters, text search and pin management.
- Moved pin preferences from browser-local storage into local `pins.json`, scoped by SteamID64 and AppID so the normal browser dashboard and OBS Browser Source share the same pins.
- Added one-time migration of v1.4.0 OBS-local pinned achievements when the new overlay first loads in OBS.
- Added same-origin API endpoints for reading and updating pins, with a hard three-pin limit and validation against the current game's achievements.
- Updated setup links and documentation to explain the split between the OBS widget and dashboard.
