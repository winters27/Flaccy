# Flaccy Web

Flaccy is a web-based frontend for downloading FLAC (lossless) music via the Qobuz API. It was built to run on a self-hosted Ubuntu server and can be accessed securely from anywhere via Cloudflare Tunnel.

### Purpose and Use Case

Flaccy was developed to make it easy to download FLAC (lossless) music directly to a home server's music collection from anywhere.

When used in combination with a home-hosted music server such as **Roon**, **Navidrome**, **Jellyfin**, or **Plex**, which monitors a shared directory, Flaccy allows you to remotely request a track and have it appear in your library almost instantly. As long as your media server is set to periodically rescan its music directory, the new files will be picked up and indexed automatically.

This workflow replicates the convenience of a commercial streaming service. You request a song, and moments later it becomes available in your own personal music library—fully lossless and privately hosted.

---

## Installation on Ubuntu Server

This guide walks through setting up Flaccy on an Ubuntu 22.04+ server.

### Step 1: Clone the Repository

```bash
git clone https://github.com/winters27/Flaccy.git
cd Flaccy
```

### Step 2: Set Up a Virtual Environment

```bash
sudo apt update
sudo apt install python3-venv -y
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Python Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment

The application requires a Qobuz user authentication token to function.

1.  **Create the environment file:**
    Copy the template to a new `.env` file:
    ```bash
    cp .env.template .env
    ```

2.  **Add your token:**
    Open `.env` in a text editor and replace `"YOUR_TOKEN_HERE"` with your actual Qobuz token.

    To get your token, log in to the Qobuz website, open your browser's developer tools, and look for the `user_auth_token` in the cookies for the `qobuz.com` domain.

---

## Running Flaccy

### Option A: Development (Manual Start)

```bash
gunicorn --workers 3 --bind unix:/home/your_user/flaccy/flaccy.sock -m 007 app:app
```

### Option B: Production with systemd

Create a systemd service file:

```bash
sudo nano /etc/systemd/system/flaccy.service
```

Paste the following (update paths as needed):

```ini
[Unit]
Description=Gunicorn instance to serve Flaccy
After=network.target

[Service]
User=your_user
Group=www-data
WorkingDirectory=/home/your_user/flaccy
Environment="PATH=/home/your_user/flaccy/venv/bin"
ExecStart=/home/your_user/flaccy/venv/bin/gunicorn --workers 3 --worker-class gevent --bind unix:/home/your_user/flaccy/flaccy.sock -m 007 --timeout 300 app:app

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl start flaccy
sudo systemctl enable flaccy
```

---

## Reverse Proxy with Nginx

Install Nginx:

```bash
sudo apt install nginx -y
```

Create an Nginx config:

```bash
sudo nano /etc/nginx/sites-available/flaccy
```

Paste:

```nginx
server {
    listen 80;
    server_name flaccy.yourdomain.com;

    location / {
        proxy_pass http://unix:/home/your_user/flaccy/flaccy.sock;
        include proxy_params;
    }
}
```

Enable the site and restart Nginx:

```bash
sudo ln -s /etc/nginx/sites-available/flaccy /etc/nginx/sites-enabled
sudo nginx -t
sudo systemctl restart nginx
```

---

## Secure Access with Cloudflare Tunnel

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
    service: http://localhost
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

1. Writable by your system user (`your_user`)
2. Traversable by `cloudflared` and `gunicorn` (if accessing outside docker volumes)

For example:

```bash
sudo chmod +x /var/lib/docker
sudo chown -R your_user:www-data /your/target/music/folder
```

---

## Automated Setup Script

You can use the following one-liner to install Flaccy interactively:

```bash
bash <(curl -s https://raw.githubusercontent.com/winters27/Flaccy/main/install.sh)
```

This script will prompt you to fill in:

- Your Ubuntu username
- The domain you want to use
- The full path to where the project will be installed

It then installs Python, Nginx, Gunicorn, sets up systemd, and configures Cloudflare Tunnel.

---

## License

This project is for personal use and research. Respect Qobuz’s terms of service.
