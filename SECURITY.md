# Security Policy

## Reporting a vulnerability

Please do not publish API keys, personal Steam account data, or details that could put another user at risk in a public issue.

For a security concern, use GitHub's **Report a vulnerability** option on this repository (Security tab), where available. If private vulnerability reporting is unavailable, contact the repository owner privately through GitHub before disclosing details publicly.

Include the affected version, steps to reproduce, expected behavior, and the potential impact. Do not include your Steam Web API key or `config.json`.

## Credential handling

The Steam Web API key is stored locally in `config.json` as plaintext. Keep that file private and do not commit it. If it is exposed, revoke it through the Steam Web API key page and create a replacement.

The helper binds to IPv4 loopback (`127.0.0.1`) and is intended for use on a trusted local PC. It is not designed to be exposed to the public internet.
