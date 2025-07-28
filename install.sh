#!/bin/bash

set -e

echo "Starting Flaccy installation and updater..."

# Variables
APP_NAME="flaccy"
APP_DIR="$HOME/flaccy"
GIT_REPO="https://github.com/winters27/flaccy.git"
SERVICE_FILE="/etc/systemd/system/$APP_NAME.service"
PYTHON_BIN="python3"
VENV_DIR="$APP_DIR/venv"
SOCK_FILE="$APP_DIR/$APP_NAME.sock"
USER=$(whoami)

# Clone or pull latest
if [ -d "$APP_DIR" ]; then
  echo "Updating existing repo..."
  cd "$APP_DIR"
  git fetch --all
  git reset --hard origin/main

  # Restore personal app.py if it exists
  if [ -f "app.py.personal" ]; then
    echo "Restoring personal app configuration..."
    cp app.py.personal app.py
  fi
else
  echo "Cloning repository..."
  git clone "$GIT_REPO" "$APP_DIR"
  cd "$APP_DIR"
fi

# Set up Python venv
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment..."
  sudo apt update
  sudo apt install python3-venv -y
  $PYTHON_BIN -m venv venv
fi

# Activate and install dependencies
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

# .env setup
if [ ! -f ".env" ]; then
  if [ -f ".env.template" ]; then
    echo "Creating .env from template..."
    cp .env.template .env
    echo "⚠️  Please edit .env and add your Qobuz auth token before running the app."
  else
    echo "⚠️  .env.template not found. Cannot create .env file."
  fi
fi

# Create systemd service
if [ ! -f "$SERVICE_FILE" ]; then
  echo "Creating systemd service for $APP_NAME..."
  sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Gunicorn instance to serve Flaccy
After=network.target

[Service]
User=$USER
Group=www-data
WorkingDirectory=$APP_DIR
Environment="PATH=$VENV_DIR/bin"
ExecStart=$VENV_DIR/bin/gunicorn --workers 3 --bind unix:$SOCK_FILE -m 007 app:app

[Install]
WantedBy=multi-user.target
EOF

  sudo systemctl daemon-reload
  sudo systemctl enable "$APP_NAME"
fi

# Restart the service
echo "Restarting $APP_NAME service..."
sudo systemctl restart "$APP_NAME"
sudo systemctl status "$APP_NAME" --no-pager

echo "✅ Flaccy is installed and running."
