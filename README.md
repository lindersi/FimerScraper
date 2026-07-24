# FimerScraper

Scrapes Fimer/ABB inverter data from the web GUI and publishes it via MQTT.
Stack: Python 3, Playwright, paho-mqtt.

## Setup

```bash
git clone https://github.com/lindersi/FimerScraper.git
cd FimerScraper
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp secrets.example.py secrets.py   # edit with real values
chmod 600 secrets.py
```

## Run

```bash
./venv/bin/python app.py
```

Or use the systemd unit on Linux (see below).

## MQTT

| Topic | Purpose |
|-------|---------|
| `fimer/#` | Data and status |
| `fimer/control/delay` | Scrape interval (seconds) |
| `fimer/control/waittime` | Retry wait (minutes) |
| `fimer/control/onoff` | `stop` / `restart` |
| `fimer/status` | Status messages |

## systemd

```ini
[Unit]
Description=Fimer-Scraper Service
After=network-online.target
Wants=network-online.target

[Service]
User=YOUR_USERNAME
Group=YOUR_USERNAME
WorkingDirectory=/home/YOUR_USERNAME/path/to/FimerScraper
ExecStart=/home/YOUR_USERNAME/path/to/FimerScraper/venv/bin/python -u app.py
Restart=always
RestartSec=10s
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

## Secrets

Never commit `secrets.py`. Use `secrets.example.py` as the template.
