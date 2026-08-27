# DiceFrame Application Updates

[中文](../zh/updates.md) | English

This page explains how to update DiceFrame itself. Plugins are updated separately through the Plugin Store.

## Installation Methods

| Installation | How to update |
|---|---|
| Windows portable | Check, download, and apply updates from Settings |
| Extracted source release | Apply the update from Settings, then restart manually |
| Git checkout | Run `git pull` after receiving a new-version notification |
| Managed Docker / NAS | Download, apply, and automatically roll back from Settings |
| Legacy Docker image or base-runtime update | Pull the latest image and recreate the container |

Updating the application does not delete saves or settings. Backing up the complete `data/` folder before an upgrade is still recommended.

## Windows Portable

Open **Settings → Version Update**, then follow the prompts to download and apply the update. DiceFrame restarts automatically and refreshes the page when the update finishes.

If the new version cannot start correctly, DiceFrame automatically returns to the previous version. Downloaded packages and older unused versions are removed after a successful update.

Portable installations keep at most two application payloads. The root-level `app/` and `python/` directories from the original archive count as the first payload and remain as the rollback copy after the first update. After the second and later successful updates, only the current and previous payloads under `versions/` are kept, and the legacy root-level `app/` and `python/` directories are removed. `data/`, `logs/`, and the root launcher are not version payloads and are never removed by this cleanup. User-installed plugin source code lives under `data/plugin-packages/` and is preserved with `data/` across versions; `app/plugins/` holds only built-in and example plugins and is cleared with old version payloads. If the current payload is unavailable, the launcher uses the version pointer to try the previous payload.

DiceFrame keeps console output while also writing persistent runtime logs. Windows portable installations use the root-level `logs/` directory, managed Docker uses persistent `data/logs/`, and source runs default to the project-root `logs/` directory. Logs rotate daily and retain the latest 30 days. They can also be removed from **Settings → Advanced → Runtime logs**. Runtime logs are independent from game history, chat history, and saves.

If Settings shows a new version but no Apply button, manually download the latest portable package from GitHub Releases once. Later updates can then be applied from Settings.

## Source Release

A source package downloaded and extracted from GitHub Releases can be updated from Settings. Restart DiceFrame manually when prompted.

DiceFrame backs up the previous application files and attempts to restore them if the update fails. Only the latest backup is kept after a successful update, and saves and settings are not overwritten.

If you use a Git checkout, continue updating it with `git pull`.

## Docker and NAS

Docker users must manually pull one baseline image that supports managed updates. Its stable launcher manages the current and previous application payloads under `data/_updater/docker-versions/`. After that migration, ordinary DiceFrame application releases can be downloaded and applied from **Settings → Version Update**. The container ID stays unchanged, and a candidate is committed only after its health check and probation period succeed; otherwise the launcher returns to the previous version.

Every Docker Update manifest must explicitly declare `data_rollback_safe: true`, meaning data written by that release remains readable by the previous application version. Managed update rejects packages without that declaration and releases with irreversible data migrations. Those releases require a base-image upgrade with an explicit backup or migration procedure instead of pretending to be an automatically reversible ordinary update.

Python ABI, system library, CA, font, or launcher protocol changes remain base-runtime updates and still require pulling a new image. DiceFrame never mounts the Docker socket and does not control the Docker daemon from inside the container.

For a Docker Compose deployment, run:

```bash
cd /path/to/diceframe  # Must contain docker-compose.yml
docker compose pull
docker compose up -d
```

`no configuration file provided: not found` means the current directory has no Compose file. Change to the original deployment directory and retry. If the container was originally started with `docker run`, pull the new image and recreate it with the original ports, volumes, and environment variables instead of applying Compose commands.

NAS users can use the device's container manager to check for updates, pull the latest image, and recreate the container. Make sure `data/` is mounted from the host.

Saves, settings, and user plugins remain under `data/`. `data/_updater/docker-versions/` contains reconstructable application payloads and may be excluded from backups; do not remove `_updater/current.json` by itself. Traditional image updates remain supported, and each image uses the byte-identical Docker application update asset from the corresponding GitHub Release as its seed.

For an image built from a local source checkout, pull the new source and run:

```bash
docker compose up -d --build
```

## Troubleshooting

### Update check returns HTTP 403

The temporary anonymous request quota for the mirrors and GitHub may be exhausted. This affects only version checks, not games, saves, or model calls. Retry later or check GitHub Releases directly.

### An update fails

Do not delete `data/`. Portable and managed-Docker installations attempt to return to the previous version automatically, while source installations attempt to restore the previous application files. If DiceFrame still cannot start, download the appropriate package again from GitHub Releases and keep the logs for diagnosis.
