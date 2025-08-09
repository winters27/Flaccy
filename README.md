

# Flaccy

*A self‑hosted web frontend that lets you search streaming catalogs and pull lossless files straight into your home music library.*

> **One‑liner:** Add tracks from anywhere and have them appear in your library moments later.

---

## Why Flaccy?

Commercial streaming is convenient, but your own library is forever. Flaccy bridges the gap by providing a clean web UI and automation around a downloader so you can request albums/tracks/playlists remotely and have them land in the folder your media server watches.

---

## Features

- **Search & add** albums, tracks, and playlists from supported services.
- **Real‑time progress** with status toasts and a live queue.
- **Playlist ingest** (upload a file and let Flaccy fetch everything).
- **Docker‑first deployment** with sample `docker-compose.yml` and Nginx config.
- **Remote‑friendly**: works great behind Cloudflare Tunnel / any reverse proxy.

---

## Supported services

- **Qobuz** (stable)
- **Tidal** (stable)
- **KKBox** (stable)
- **Any OrpheusDL module** — drop in the module and set credentials to extend support.

---

## Quick start (Docker)

> Requires **Docker** and **Docker Compose**, plus **FFmpeg** on the host.

```bash
# 1) Clone
git clone https://github.com/winters27/flaccy.git
cd flaccy

# 2) Create your env file
cp .env.template .env
# then edit .env with your credentials

# 3) Bring it up
docker compose up --build -d

# 4) Open the UI
# http://localhost:5000 (or your reverse-proxied hostname)
```

### Environment variables

Copy `.env.template` to `.env` and set as needed:

- `QOBUZ_EMAIL`, `QOBUZ_PASSWORD`, `QOBUZ_APP_ID`, `QOBUZ_APP_SECRET`
- `TIDAL_USER`, `TIDAL_PASS`
- `KKBOX_EMAIL`, `KKBOX_PASSWORD` *(or relevant module vars)*
- `MUSIC_DIR` – absolute path inside the container where downloaded files are written
- `WORKERS` – Gunicorn worker count
- `SECRET_KEY` – session/signing key for the web app

---

## Volumes & ports (compose)

The provided `docker-compose.yml` exposes port **5000** by default and mounts `./downloads` to the container’s music directory. Adjust paths/ports to taste.

---

## Local development

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python run.py
# UI at http://localhost:5000
```

---

## Reverse proxy (optional)

A sample `nginx.conf` is included. Point your proxy at the app’s upstream (port 5000). Make sure to forward `X-Forwarded-*` headers and set sensible timeouts for long downloads.

### Using Cloudflare with Flaccy

If you want to expose Flaccy securely via Cloudflare:

1. **Generate Cloudflare Origin Certificates (.pem files)** for the domain you want to use.
   - In the Cloudflare dashboard, navigate to **SSL/TLS > Origin Server > Create Certificate**.
   - Select “Let Cloudflare generate a private key and CSR” and download both the certificate and private key.
2. On the **host machine**, create the directory for the keys:

```bash
sudo mkdir -p /etc/ssl/cf_origin
```

3. Place the downloaded files into:

```bash
/etc/ssl/cf_origin/fullchain.pem
/etc/ssl/cf_origin/privkey.pem
```

These paths match the defaults in the provided `nginx.conf`:

```
ssl_certificate /etc/ssl/cf_origin/fullchain.pem;
ssl_certificate_key /etc/ssl/cf_origin/privkey.pem;
```

4. Update your reverse proxy config (if needed) to reference these paths.
5. In your Cloudflare dashboard, create an **A record** for your domain pointing to the public IPv4 address of the host machine.

These steps are required for Cloudflare’s SSL and DNS to work correctly with your self‑hosted reverse proxy.

---

## How it fits together

```
[Browser]
   ⇅
[Flaccy Web UI] — REST calls — [Download worker (OrpheusDL + modules)]
                                  │
                                  └── writes → [MUSIC_DIR] (host mount)
```

- The UI requests a job; the worker fetches audio + tags via OrpheusDL modules (Qobuz/Tidal/KKBox/etc.), converts if needed with FFmpeg, and writes to `MUSIC_DIR`.
- Your media server scans that folder and the new music appears.

---

## Permissions & storage

If `MUSIC_DIR` is a bind mount (e.g., a NAS, Nextcloud volume, or external drive), ensure the UID/GID used by the container can write to it.

---

## Security notes

- Keep the app behind authentication (reverse proxy auth, VPN, or Cloudflare Access).
- Treat your `.env` like a password vault; never commit it.
- Respect providers’ terms of service and your local laws.

---

## Screenshots

> 

---

## Roadmap

-

---

## Troubleshooting

- **Nothing shows up in my library** → verify your media server watches `MUSIC_DIR`.
- **Permissions error on write** → check container user vs. host folder ownership.
- **Stuck jobs** → restart just the worker or the stack.
- **FFmpeg not found** → ensure FFmpeg is installed on the host.

---

## Credits

Built on the excellent **OrpheusDL** project and its modules.

---

## License

This project is licensed under the [MIT License](LICENSE).

