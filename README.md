# Flaccy Web

This is the web version of the Flaccy application, designed to be hosted on a home server and accessed from anywhere.

## 1. Project Setup

These instructions are for an Ubuntu server.

### 1.1. Clone the Repository

First, get the code onto your server. If you're using Git, you can clone it. Otherwise, simply copy the files.

```bash
git clone <your-repo-url>
cd FlaccyWEB
```

### 1.2. Create a Virtual Environment

It's a best practice to use a virtual environment to manage project-specific dependencies.

```bash
sudo apt update
sudo apt install python3-venv -y
python3 -m venv venv
source venv/bin/activate
```

### 1.3. Install Dependencies

Install the required Python packages using the `requirements.txt` file.

```bash
pip install -r requirements.txt
```

## 2. Running the Application

For development, you can run the Flask app directly. For production, it's highly recommended to use a proper WSGI server like Gunicorn.

### 2.1. Running with Gunicorn (Recommended for Production)

Gunicorn is a robust and efficient WSGI server for running Python web applications.

```bash
pip install gunicorn
gunicorn --workers 4 --bind 0.0.0.0:5000 app:app
```

This command will start the application on port 5000. It will be accessible from other devices on your local network.

### 2.2. Running in the Background with `systemd`

To ensure your application runs continuously and restarts automatically, you can create a `systemd` service.

**Create a service file:**

```bash
sudo nano /etc/systemd/system/flaccy.service
```

**Add the following content to the file.** Make sure to replace `/path/to/your/FlaccyWEB` with the actual path to your project directory.

```ini
[Unit]
Description=Gunicorn instance to serve Flaccy
After=network.target

[Service]
User=your_username
Group=www-data
WorkingDirectory=/path/to/your/FlaccyWEB
Environment="PATH=/path/to/your/FlaccyWEB/venv/bin"
ExecStart=/path/to/your/FlaccyWEB/venv/bin/gunicorn --workers 4 --bind 0.0.0.0:5000 app:app

[Install]
WantedBy=multi-user.target
```

**Enable and start the service:**

```bash
sudo systemctl daemon-reload
sudo systemctl start flaccy
sudo systemctl enable flaccy
```

You can check the status of the service with `sudo systemctl status flaccy`.

## 3. Exposing to the Web with Cloudflare Tunnel

Cloudflare Tunnel (`cloudflared`) creates a secure, outbound-only connection to the Cloudflare network, allowing you to expose your local server to the internet without opening up firewall ports.

### 3.1. Install `cloudflared`

Follow the official Cloudflare documentation to install `cloudflared` on your Ubuntu server. You can find the latest instructions [here](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/).

### 3.2. Authenticate `cloudflared`

Run the following command and follow the instructions to link `cloudflared` to your Cloudflare account:

```bash
cloudflared tunnel login
```

### 3.3. Create a Tunnel

Choose a name for your tunnel (e.g., `flaccy-tunnel`) and create it:

```bash
cloudflared tunnel create flaccy-tunnel
```

This will generate a credentials file (usually in `~/.cloudflared/`) and give you a Tunnel ID.

### 3.4. Configure the Tunnel

Create a configuration file for your tunnel. The default location is `~/.cloudflared/config.yml`.

```bash
nano ~/.cloudflared/config.yml
```

Add the following content, replacing `<YOUR_TUNNEL_ID>` with the ID from the previous step:

```yaml
tunnel: <YOUR_TUNNEL_ID>
credentials-file: /home/your_username/.cloudflared/<YOUR_TUNNEL_ID>.json
ingress:
  - hostname: flaccy.winters.app
    service: http://localhost:5000
  - service: http_status:404
```

### 3.5. Route DNS to the Tunnel

In your Cloudflare dashboard, go to your domain (`winters.app`) and create a CNAME record for `flaccy` that points to your tunnel's ID followed by `.cfargotunnel.com`.

- **Type:** CNAME
- **Name:** `flaccy`
- **Target:** `<YOUR_TUNNEL_ID>.cfargotunnel.com`

### 3.6. Run the Tunnel

You can run the tunnel as a `systemd` service to ensure it's always active.

```bash
sudo cloudflared service install
sudo systemctl start cloudflared
```

Your Flaccy application should now be accessible at `https://flaccy.winters.app`.
