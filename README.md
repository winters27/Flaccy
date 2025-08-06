# Flaccy Web

Flaccy is a sleek, self-hosted web application for downloading high-quality music from multiple services. It is designed to integrate seamlessly with your home media server, allowing you to expand your personal music library from anywhere.

### Key Features

- **Multi-Service Support**: Download from both **Tidal** and **Qobuz**.
- **Modern Web UI**: A clean, responsive interface for searching, downloading, and managing your music.
- **Real-Time Progress**: Track download progress in real-time with toast notifications.
- **Playlist Support**: Upload a playlist file and let Flaccy handle the rest.
- **Dockerized**: Easy to deploy and manage with Docker and Docker Compose.
- **Secure Remote Access**: Includes instructions for setting up secure remote access with Cloudflare Tunnel.

### Purpose and Use Case

Flaccy was developed to make it easy to download lossless and high-resolution music directly to a home server's music collection from anywhere.

When used in combination with a home-hosted music server such as **Roon**, **Navidrome**, **Jellyfin**, or **Plex**, which monitors a shared directory, Flaccy allows you to remotely request a track or album and have it appear in your library almost instantly. As long as your media server is set to periodically rescan its music directory, the new files will be picked up and indexed automatically.

This workflow replicates the convenience of a commercial streaming service. You request a song, and moments later it becomes available in your own personal music library—fully lossless and privately hosted.

---

## Dependencies

### FFmpeg

`ffmpeg` is required for processing audio files. Please install it on your system before running Flaccy.

**Windows (using winget):**
```bash
winget install -e --id Gyan.FFmpeg
```

**macOS (using Homebrew):**
```bash
brew install ffmpeg
```

**Linux (using apt):**
```bash
sudo apt update && sudo apt install ffmpeg
```

---

## Installation with Docker

This guide walks through setting up Flaccy on any system with Docker and Docker Compose.

### Step 1: Clone the Repository

```bash
git clone https://github.com/winters27/Flaccy.git
cd Flaccy
```

### Step 2: Configure Environment

1.  **Create the environment file:**
    Copy the template to a new `.env` file:
    ```bash
    cp .env.template .env
    ```

2.  **Edit the `.env` file:**
    Open the `.env` file in a text editor and configure the following variables with your credentials for the services you want to use:
    - `QOBUZ_EMAIL`
    - `QOBUZ_PASSWORD`
    - `QOBUZ_APP_ID`
    - `QOBUZ_APP_SECRET`
    - `TIDAL_USER`
    - `TIDAL_PASS`

---

## Running Flaccy

To run Flaccy, simply use Docker Compose:

```bash
docker-compose up --build -d
```

The application will be available at `http://localhost:5000`.

---

## Secure Access with Cloudflare Tunnel

For secure remote access, you can use Cloudflare Tunnel.

### Step 1: Install cloudflared

Follow the official install guide:
https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/

### Step 2: Authenticate

```bash
cloudflared tunnel login
```

### Step 3: Create a Tunnel

```bash
cloudflared tunnel create flaccy-tunnel
```

### Step 4: Configure

Create a configuration file in your home directory:

```bash
mkdir -p ~/.cloudflared
nano ~/.cloudflared/config.yml
```

Paste the following configuration into the file, replacing `<TUNNEL_ID>` and `<YOUR_TUNNEL_ID>` with the ID from the previous step, and `flaccy.yourdomain.com` with your desired hostname:

```yaml
tunnel: <TUNNEL_ID>
credentials-file: /home/brandon/.cloudflared/<YOUR_TUNNEL_ID>.json
ingress:
  - hostname: flaccy.yourdomain.com
    service: http://localhost:5000
  - service: http_status:404
```

### Step 5: DNS Routing

In your Cloudflare DNS dashboard, create a CNAME record:

-   **Type**: CNAME
-   **Name**: `flaccy` (or your desired subdomain)
-   **Target**: `<TUNNEL_ID>.cfargotunnel.com`

### Step 6: Run as a Systemd Service

To ensure the tunnel runs persistently, create a systemd service file:

```bash
sudo nano /etc/systemd/system/cloudflared.service
```

Paste the following into the file. Make sure to replace `brandon` with your username if it's different.

```ini
[Unit]
Description=Cloudflare Tunnel
After=network.target

[Service]
ExecStart=/usr/local/bin/cloudflared tunnel --config /home/brandon/.cloudflared/config.yml run
User=brandon
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Step 7: Enable and Start the Service

Now, reload the systemd daemon, and enable and start the `cloudflared` service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now cloudflared.service
```

You can check the status of the service with:

```bash
sudo systemctl status cloudflared.service
```

---

## Permissions Note

If you are downloading music to a shared media directory (such as a Nextcloud volume or mounted drive), ensure that the target directory is writable by the user running the Docker container.

---

## License

This project is for personal use and research. Respect the terms of service of the music providers.
