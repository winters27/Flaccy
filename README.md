# Flaccy Web

Flaccy is a web-based frontend for downloading FLAC (lossless) music via the Qobuz API. It was built to run on a self-hosted Ubuntu server and can be accessed securely from anywhere via Cloudflare Tunnel.

### Purpose and Use Case

Flaccy was developed to make it easy to download FLAC (lossless) music directly to a home server's music collection from anywhere.

When used in combination with a home-hosted music server such as **Roon**, **Navidrome**, **Jellyfin**, or **Plex**, which monitors a shared directory, Flaccy allows you to remotely request a track and have it appear in your library almost instantly. As long as your media server is set to periodically rescan its music directory, the new files will be picked up and indexed automatically.

This workflow replicates the convenience of a commercial streaming service. You request a song, and moments later it becomes available in your own personal music library—fully lossless and privately hosted.

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
    Open the `.env` file in a text editor and configure the following variables:
    - `FLACCY_PASSWORD`: Set a password to protect the web interface.
    - `SECRET_KEY`: A random string for session security. You can generate one with `openssl rand -hex 16`.
    - `DOWNLOAD_DIRECTORY`: The absolute path where your music will be saved.
    - `UID`: The user ID to run the container as. Find it with `id -u`.
    - `GID`: The group ID to run the container as. Find it with `id -g`.
    
    After logging into the Flaccy web interface, you will be prompted to log in with your Qobuz credentials.

---

## Running Flaccy

To run Flaccy, simply use Docker Compose:

```bash
docker-compose up --build -d
```

The application will be available at `http://localhost:5001`.

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

Create a config:

```bash
sudo mkdir -p /etc/cloudflared
sudo nano /etc/cloudflared/config.yml
```

Paste:

```yaml
tunnel: <TUNNEL_ID>
credentials-file: /etc/cloudflared/<TUNNEL_ID>.json
ingress:
  - hostname: flaccy.yourdomain.com
    service: http://localhost:5001
  - service: http_status:404
```

### Step 5: DNS Routing

In Cloudflare DNS dashboard:

- Type: CNAME  
- Name: `flaccy`  
- Target: `<TUNNEL_ID>.cfargotunnel.com`

### Step 6: Run as Service

```bash
sudo cloudflared service install
sudo systemctl start cloudflared
sudo systemctl enable cloudflared
```

---

## Permissions Note

If you are downloading music to a shared media directory (such as a Nextcloud volume or mounted drive), ensure that the target directory is:

1. Writable by the user specified by `UID` and `GID` in your `.env` file.

For example:

```bash
sudo chown -R $(id -u):$(id -g) /your/target/music/folder
```

---

## License

This project is for personal use and research. Respect Qobuz’s terms of service.
