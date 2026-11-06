# 🧟 Resident Evil 2 — Steam Achievement Overlay

<p align="center">
  <strong>A real-time Steam achievement tracker for Resident Evil 2 (2019), built for OBS.</strong>
  <br>
  Track your journey towards 100% completion and let your viewers follow every achievement as you unlock it.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-blue?style=for-the-badge" alt="Windows">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/OBS-Browser%20Source-purple?style=for-the-badge&logo=obsstudio&logoColor=white" alt="OBS Browser Source">
  <img src="https://img.shields.io/badge/Dependencies-None-success?style=for-the-badge" alt="No external dependencies">
</p>

---

## 📖 Table of Contents

- [✨ Features](#-features)
- [📋 Requirements](#-requirements)
- [🚀 Getting Started](#-getting-started)
  - [1. Installation](#1-installation)
  - [2. Connect Steam](#2-connect-steam)
  - [3. Add to OBS](#3-add-to-obs)
- [🔄 Synchronization](#-synchronization)
- [🔌 Steam API Integration](#-steam-api-integration)
- [🔒 Security & Privacy](#-security--privacy)
- [🛠️ Troubleshooting](#️-troubleshooting)
- [🧪 Running Tests](#-running-tests)
- [❤️ Credits & Disclaimer](#️-credits--disclaimer)

---

## ✨ Features

Everything you need to bring your Resident Evil 2 achievement hunt to your stream.

- 🏆 **Live Achievement Tracking** – Automatically retrieves your Steam achievements and unlock status.
- 📊 **Completion Counter** – Displays your overall achievement progress.
- 🔍 **Achievement Filters** – Easily distinguish between unlocked and locked achievements.
- 🖼️ **Achievement Details** – Displays icons, names and descriptions.
- 🔔 **Unlock Notifications** – Notifies your viewers whenever you unlock a new achievement.
- 🔄 **Automatic Synchronization** – Checks for newly unlocked achievements every 30 seconds.
- 💾 **Smart Caching** – Caches achievement definitions for up to six hours to reduce unnecessary API requests.
- 🛡️ **Reliable Offline Handling** – Preserves your last successful achievement data during temporary Steam outages.
- ⚡ **Automatic Recovery** – Uses retry backoff when Steam is unavailable.
- 🎮 **OBS Integration** – Designed to work as a transparent OBS Browser Source.

**No unnecessary dependencies.** The backend uses only Python's standard library. No `pip install` required.

---

## 📋 Requirements

Before getting started, make sure you have:

| Requirement | Details |
|---|---|
| Operating System | Windows 10 or Windows 11 |
| Python | Version 3.10 or newer |
| Game | Resident Evil 2 (2019) on Steam |
| Steam API | A Steam Web API key |
| Steam Account | Your Steam profile URL or SteamID64 |
| Streaming Software | OBS Studio with Browser Source support |

---

## 🚀 Getting Started

### 1. Installation

1. Download the latest project ZIP from the [GitHub Releases](../../releases) page, or download the repository.
2. Extract the ZIP into a permanent folder.

   Example:

   `C:\RE2AchievementOverlay\`

3. Double-click `start_overlay.bat`.
4. Your browser should open the local setup page:

   **http://127.0.0.1:8765/**

> **Windows Security Notice**
>
> Windows may display an "Unknown Publisher" warning when launching `start_overlay.bat`. This is expected because the batch file is not digitally signed. It is not a malware detection.
>
> You can inspect the source code in this repository before running it.

### 2. Connect Steam

1. Visit the [Steam Web API Key registration page](https://steamcommunity.com/dev/apikey/).
2. Sign in with your Steam account.
3. Register for a Web API key.
4. Copy your API key.
5. Return to the overlay setup page.
6. Enter your Steam API key and Steam profile URL (or SteamID64).
7. Click **Connect Steam**.

**Important:** Your Steam profile and **Game Details** privacy settings must be set to **Public** if Steam cannot return your achievements.

Your API key is saved locally in `config.json`. The helper uses it to communicate with Steam. It is never sent to the OBS overlay page or displayed to viewers.

Never publish, share or commit `config.json`. The repository's `.gitignore` excludes it by default.

The configuration file is stored as ordinary local JSON, not encrypted. Anyone with access to your Windows account or files may be able to read it. Keep your Windows account protected and use the overlay only on a trusted PC.

### 3. Add to OBS

1. Open OBS Studio.
2. Add a new **Browser Source**.
3. Set its URL to:

   ```text
   http://127.0.0.1:8765/overlay
   ```

4. Use the following dimensions as a starting point:

   | Setting | Value |
   |---|---|
   | Width | 440 |
   | Height | 820 |

5. Leave **Shutdown source when not visible** unchecked if you want the overlay ready whenever you show it.
6. Position and resize the source to fit your stream layout.

The overlay background is transparent, allowing you to position it over your gameplay without covering the entire scene.

> **Keep the helper running!**
>
> The command window must remain open while streaming. It handles Steam synchronization and serves the overlay locally.
>
> Closing the command window stops the helper.

---

## 🔄 Synchronization

The overlay automatically synchronizes your achievement progress with Steam.

| Behavior | Details |
|---|---|
| Achievement schema | Cached for up to 6 hours |
| Achievement polling | Every 30 seconds |
| Retry behavior | Exponential backoff, up to 5 minutes |
| Steam outages | Last successful achievement list is preserved |
| Stale data | Overlay indicates when displayed data is outdated |
| First connection | Existing achievements are treated as the initial baseline |

**How unlock notifications work:**

When connecting for the first time, your existing achievements are registered as your baseline. This prevents the overlay from triggering notifications for achievements you unlocked before starting the stream.

After the initial synchronization, newly detected achievements trigger notifications for your viewers.

---

## 🔌 Steam API Integration

The project uses the official Steam Web API to retrieve achievement information.

The following API methods are used:

| API Method | Purpose |
|---|---|
| `ISteamUser/ResolveVanityURL` | Resolves custom Steam profile URLs |
| `ISteamUserStats/GetSchemaForGame` | Retrieves achievement names, descriptions and icons |
| `ISteamUserStats/GetPlayerAchievements` | Retrieves the player's achievement unlock status |

For further information, see the official [Steamworks ISteamUserStats documentation](https://partner.steamgames.com/doc/webapi/ISteamUserStats).

---

## 🔒 Security & Privacy

Security matters, especially when distributing software to other people.

The project includes the following protections:

- **Localhost Only:** The helper binds to `127.0.0.1`. It is not exposed to your LAN or the public internet.
- **Request Validation:** Setup and manual-refresh POST requests require the expected local Host and Origin, helping prevent cross-origin websites from modifying the saved Steam account.
- **Input Validation:** Steam API key formats, SteamID64 values and Steam Community profile hosts are validated.
- **Private Responses:** Responses containing account information use `Cache-Control: no-store`.
- **Safe Logging:** Request logs omit query strings and request bodies, preventing credentials from being written to console logs.
- **Local Credentials:** The Steam API key stays in `config.json` and is never exposed to the OBS overlay page.

### Protecting Your Steam API Key

Your Steam API key is stored in plaintext in `config.json`.

- Never upload `config.json` to GitHub.
- Never share your API key publicly.
- Keep your Windows account protected.
- Revoke your API key at the [Steam Web API Key page](https://steamcommunity.com/dev/apikey/) if it is accidentally exposed.

---

## 🛠️ Troubleshooting

<details>
<summary><strong>Could not resolve Steam profile</strong></summary>

Make sure you provide either your full Steam Community profile URL:

`https://steamcommunity.com/id/yourusername/`

Or your 17-digit SteamID64.

</details>

<details>
<summary><strong>Could not read achievements</strong></summary>

Make sure your Steam profile and Game Details privacy settings are set to **Public**.

</details>

<details>
<summary><strong>Overlay says local helper offline</strong></summary>

Make sure `start_overlay.bat` is running and that its command window remains open.

</details>

<details>
<summary><strong>Overlay says Steam data is stale</strong></summary>

Steam could not be reached during the last synchronization attempt.

Your last successful achievement list remains visible. The helper automatically retries when Steam becomes available again.

</details>

<details>
<summary><strong>Port 8765 is already in use</strong></summary>

Another application is already using the default port.

Close the conflicting application or set the `RE2_OVERLAY_PORT` environment variable before starting the batch file.

Remember to update the OBS Browser Source URL to use the same port.

</details>

---

## 🧪 Running Tests

The project includes automated backend tests to help verify functionality and prevent regressions.

From the project directory, open PowerShell and run:

```powershell
py -3 -m unittest discover -s tests -v
```

The tests use mocked Steam API responses.

**No Steam API key or internet connection is required to run the test suite.**

---

## ❤️ Credits & Disclaimer

This project uses the Steam Web API provided by **Valve Corporation** to retrieve Resident Evil 2 achievement data.

**Resident Evil 2**, including its name, trademarks, characters, artwork and other related game assets, belongs to its respective rights holders, including **Capcom**.

This is an unofficial fan-made project. It is not affiliated with, endorsed by, or sponsored by Valve Corporation or Capcom.

Made for achievement hunters and Resident Evil fans. 🧟

---

<p align="center">
  <strong>Good luck on your journey to 100% completion!</strong>
  <br>
  <sub>Made by <strong>Swifteridu</strong></sub>
</p>