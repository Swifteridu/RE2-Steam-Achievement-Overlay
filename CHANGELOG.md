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
