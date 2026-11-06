# 🎮 Steam Achievement Overlay

<p align="center">
  <strong>A real-time Steam achievement tracker for OBS Studio.</strong>
  <br>
  Choose a Steam game, connect your profile and let your viewers follow your progress towards 100% completion.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-blue?style=for-the-badge" alt="Windows 10 and 11">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/OBS-Browser%20Source-purple?style=for-the-badge&logo=obsstudio&logoColor=white" alt="OBS Browser Source">
  <img src="https://img.shields.io/badge/Dependencies-None-success?style=for-the-badge" alt="No external dependencies">
</p>

---

## 📖 Contents

- [✨ Features](#-features)
- [🎯 Game compatibility](#-game-compatibility)
- [📋 Requirements](#-requirements)
- [🚀 Getting started](#-getting-started)
- [🔄 Synchronization](#-synchronization)
- [🔌 Steam API integration](#-steam-api-integration)
- [🔒 Security and privacy](#-security-and-privacy)
- [🛠️ Troubleshooting](#️-troubleshooting)
- [🧪 Running tests](#-running-tests)
- [❤️ Credits and disclaimer](#️-credits-and-disclaimer)

---

## ✨ Features

- 🕹️ **Choose your game** – Search the Steam Store or enter a Steam AppID / Store URL.
- 🏆 **Live achievement tracking** – Retrieves the selected game's achievement definitions and your unlock status from Steam.
- 📊 **Completion counter** – Shows unlocked achievements, total achievements and completion percentage.
- 🔍 **Achievement filters** – Separate unlocked and locked achievements.
- 📌 **Pinned objectives** – Pin up to three achievements and switch between a focused pinned view and the complete achievement list. Pins are saved locally per Steam account and game.
- 🖼️ **Achievement details** – Shows Steam achievement icons, names and descriptions.
- 🔔 **Unlock notifications** – Notifies viewers when new achievements are detected. Multiple unlocks between polls are queued individually.
- 🔄 **Automatic synchronization** – Checks player progress every 30 seconds while Steam is responding.
- 💾 **Persistent schema caching** – Caches each game's achievement definitions on disk for up to six hours.
- 🛡️ **Offline handling** – Keeps the last successful achievement list visible during temporary Steam outages and marks it as stale.
- ⚡ **Automatic recovery** – Uses retry backoff when Steam is unavailable.
- 🎥 **OBS integration** – Runs as a transparent OBS Browser Source.
- 🐍 **No extra Python packages** – Uses only Python's standard library; no `pip install` step is required.

### Project structure

Backend responsibilities are split into focused modules instead of being concentrated in one file:

| Module | Responsibility |
|---|---|
| `steam_overlay/config.py` | Local configuration, validation and legacy migration |
| `steam_overlay/steam_client.py` | Steam API requests, game search and schema caching |
| `steam_overlay/service.py` | Achievement synchronization, state and unlock notifications |
| `steam_overlay/http_server.py` | Local HTTP routes and request security |
| `steam_overlay/app.py` | Application startup and shutdown |
| `server.py` | Small launcher entry point |

## 🎯 Game compatibility

Choose from Steam games in the setup page. The selected Steam AppID determines which achievement definitions and player progress the helper retrieves. Search displays a maximum of **three full-game results** at a time. DLC, demos, soundtracks, software and other non-game Store item types are filtered out using Steam AppDetails metadata. Enter an AppID or Store URL manually when your game is not among the search results.

**Important limitation:** it is not technically possible to guarantee support for literally every Steam game. A title must publish an achievement schema and player achievement data through Steamworks. Some games have no Steam achievements, do not expose the required schema, or do not make player stats available. Those titles cannot be tracked by this overlay through the Steam Web API.

Game search is limited to three results per query to keep selection quick and uncluttered. This project currently supports:

- Steam games that expose achievement definitions through `ISteamUserStats/GetSchemaForGame`.
- Player accounts whose game details and achievement data are accessible through Steam's API.
- One selected game at a time. You can switch games from the setup page.

It does **not** currently track achievements from Epic Games, GOG, PlayStation, Xbox, non-Steam games, or platform-specific achievement systems outside Steam.

### How to select a game
<img width="1919" height="1079" alt="SteamAchievementSetup" src="https://github.com/user-attachments/assets/26c9443d-cffd-4870-8d35-121b88a756e9" />
1. Search by the game's name in the setup page and select one of the up to three results; or
2. Enter its numeric Steam AppID; or
3. Paste its Steam Store URL, for example `https://store.steampowered.com/app/620/Portal_2/`.

The helper checks whether Steam returns an achievement schema when you connect. A game appearing in the Store search results does not automatically mean its achievements are accessible through the API.

## 📋 Requirements

| Requirement | Details |
|---|---|
| Operating system | Windows 10 or Windows 11 |
| Python | Version 3.10 or newer |
| Game | A Steam game with achievement data accessible through Steamworks |
| Steam API | A Steam Web API key |
| Steam account | Steam profile URL or SteamID64 |
| Streaming software | OBS Studio with Browser Source support |

## 🚀 Getting started

### 1. Installation

1. Download the latest `Steam_Achievement_Overlay` ZIP from the [Releases page](../../releases).
2. Extract the ZIP into a permanent folder, for example `C:\SteamAchievementOverlay\`.
3. Double-click `start_overlay.bat`.
4. Your browser should open the local setup page at **http://127.0.0.1:8765/**.

> **Windows security notice**
>
> Windows may display an "Unknown Publisher" warning when launching `start_overlay.bat`. The batch file is not digitally signed, so Windows cannot verify a publisher. This warning is not itself a malware detection. Review the source code before running software downloaded from the internet.

### 2. Select a game and connect Steam

1. On the setup page, search for your game and select it from the results. Alternatively, enter its Steam AppID or Steam Store URL.
2. Create a Steam Web API key at the [Steam Web API Key page](https://steamcommunity.com/dev/apikey/).
3. Enter your API key and Steam profile URL (or SteamID64).
4. Click **Connect Steam & Load Achievements**.
5. The helper verifies that the selected game exposes achievement data and then loads your progress.

Your Steam profile and **Game Details** privacy settings should be **Public** if Steam cannot return your achievement data. Some games still won't work even with public privacy settings if the developer does not expose the required stats.

The API key is saved locally in `config.json`. It is used by the local helper to communicate with Steam; it is never sent to the OBS overlay page or displayed to viewers. Do not publish, share or commit `config.json`. The repository's `.gitignore` excludes it by default.

The configuration file is stored as ordinary local JSON, not encrypted. Anyone with access to your Windows account or files may be able to read it. Use the overlay only on a trusted PC and keep your Windows account protected.

**Existing v1.1 configuration:** if you are upgrading from the original release, copy your old `config.json` into the new project folder. The helper recognizes that legacy configuration and migrates its original game selection (its previously hard-coded AppID) automatically. You can then choose another Steam game from the setup page. Never upload the config file to GitHub.

### 3. Add the overlay to OBS

1. Open OBS Studio.
2. Add a **Browser Source**.
3. Set the URL to:

   ```text
   http://127.0.0.1:8765/overlay
   ```
<img width="1919" height="1079" alt="SteamAchievementOverlay" src="https://github.com/user-attachments/assets/56afa409-9765-4c46-834d-e22d0de10037" />
4. Start with these dimensions:

   | Setting | Value |
   |---|---:|
   | Width | 560 |
   | Height | 900 |

5. Leave **Shutdown source when not visible** unchecked if you want it ready whenever you show it.
6. Position and resize the source to fit your stream layout. Avoid shrinking it too far; the overlay now uses larger text and achievement cards to remain readable at typical streaming sizes.

The area outside the panel is transparent. Keep the command window running while streaming; it hosts the overlay and synchronizes your Steam data. Close it to stop the helper.

### Pinning achievements

In the overlay, use **All Achievements** to keep browsing the full unlocked/locked list. Select the star beside any achievement to pin it; up to three can be pinned per Steam account and game. The **Pinned** view shows only those selected objectives as larger cards. Pins are stored in the OBS browser's local storage on your PC and do not change your Steam achievements.

## 🔄 Synchronization

| Behavior | Details |
|---|---|
| Achievement schema cache | Per-game cache, up to 6 hours |
| Player achievement polling | Every 30 seconds while Steam responds |
| Retry behavior | Exponential backoff, up to 5 minutes |
| Steam outages | Last successful achievement list is preserved and marked stale |
| First connection | Existing achievements are treated as the initial baseline |
| Multiple unlocks | Each newly detected achievement is queued for its own notification |
| Game/account switch | New selection becomes a baseline; old unlocks do not trigger false notifications |

The achievement schema cache is stored in the local `cache/` directory. It contains public game achievement definitions, not your Steam API key. It is excluded from Git by `.gitignore`.

## 🔌 Steam API integration

The helper uses these Steam Web API methods:

| API method | Purpose |
|---|---|
| `ISteamUser/ResolveVanityURL` | Resolves custom Steam profile URLs |
| `ISteamUserStats/GetSchemaForGame` | Retrieves the selected game's achievement names, descriptions and icons |
| `ISteamUserStats/GetPlayerAchievements` | Retrieves the selected account's achievement unlock state for that AppID |

Game-name search uses Steam Store's search endpoint. This Store search endpoint is an undocumented convenience interface and may change; if search is unavailable, enter the AppID or Store URL manually. The search service is separate from the achievement API; final compatibility is checked using the selected game's Steamworks achievement schema and player stats.

See the official [Steamworks ISteamUserStats documentation](https://partner.steamgames.com/doc/webapi/ISteamUserStats).

## 🔒 Security and privacy

- **Localhost only:** the helper binds to `127.0.0.1`; it is not exposed to your LAN or the public internet.
- **Request validation:** setup and manual-refresh POST requests require the expected local Host and Origin.
- **Input validation:** API key formats, SteamID64 values, AppIDs and Steam Community / Steam Store URL hosts are validated.
- **Private responses:** responses containing account data use `Cache-Control: no-store`.
- **Safe logging:** request logs omit query strings and request bodies, so credentials are not written to the console log.
- **Local credentials:** the Steam API key is stored in `config.json` as plaintext. Keep that file private and out of GitHub.

If you accidentally expose your API key, revoke it through the [Steam Web API Key page](https://steamcommunity.com/dev/apikey/) and create a replacement. See [SECURITY.md](SECURITY.md) for vulnerability-reporting guidance.

## 🛠️ Troubleshooting

<details>
<summary><strong>Steam search cannot find my game</strong></summary>

Try entering the numeric AppID from the Steam Store URL instead. For example, in `https://store.steampowered.com/app/620/Portal_2/`, the AppID is `620`.

</details>

<details>
<summary><strong>Steam says the game does not expose an achievement schema</strong></summary>

The game may not have Steam achievements, or its developer may not publish the achievement schema through Steamworks. This cannot be fixed by changing your privacy settings. Try another game that exposes its achievement data.

</details>

<details>
<summary><strong>Could not read my achievements</strong></summary>

Set your Steam profile and **Game Details** privacy settings to **Public**. Also check that you own or have access to the selected game and that Steam can return its player stats.

</details>

<details>
<summary><strong>The overlay says local helper offline</strong></summary>

Run `start_overlay.bat` and keep its command window open.

</details>

<details>
<summary><strong>The overlay says Steam data is stale</strong></summary>

Steam could not be reached during the last synchronization attempt. Your last successful achievement list remains visible, and the helper retries automatically.

</details>

<details>
<summary><strong>Port 8765 is already in use</strong></summary>

Close the other local service using that port, or set the `STEAM_OVERLAY_PORT` environment variable before starting the batch file. Update the OBS Browser Source URL to use the same port.

</details>

## 🧪 Running tests

From the project directory, open PowerShell and run:

```powershell
py -3 -m unittest discover -s tests -v
```

The tests use mocked Steam responses. No Steam API key or internet connection is required. GitHub Actions also runs the test suite on pushes and pull requests against Python 3.10–3.14.

## ❤️ Credits and disclaimer

This project uses the Steam Web API provided by **Valve Corporation** and Steam Store search to locate games. Game achievement definitions, icons and related metadata are retrieved from Steam.

All game names, trademarks, artwork and other game assets belong to their respective rights holders. This is an unofficial community project and is not affiliated with, endorsed by, or sponsored by Valve Corporation or any game developer or publisher.

The project code is distributed under the [MIT License](LICENSE).

Steam achievement support depends on what each game's developer exposes through Steamworks. This tool does not modify game files or unlock achievements.

---

<p align="center">
  <strong>Track your games. Share your progress. Go for 100%.</strong>
  <br>
  <sub>Made by <strong>Swifteridu</strong></sub>
</p>
