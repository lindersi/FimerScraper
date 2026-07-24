# FimerScraper

Scrapes Fimer/ABB inverter data from the web GUI and publishes it via MQTT.
Stack: Python 3, Playwright, paho-mqtt. Typical deploy: **venv + systemd**.

## Setup

```bash
git clone https://github.com/lindersi/FimerScraper.git
cd FimerScraper
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# Install Chromium for Playwright (and OS deps on Linux if prompted):
playwright install chromium
playwright install-deps chromium   # Linux only; needs sudo
cp secrets.example.py secrets.py   # edit with real values
chmod 600 secrets.py
```

Smoke test:

```bash
./venv/bin/python -u app.py
```

Stop with Ctrl+C, or publish `stop` to `fimer/control/onoff`.

## MQTT

| Topic | Purpose |
|-------|---------|
| `fimer/#` | Data and status |
| `fimer/control/delay` | Scrape interval (seconds) |
| `fimer/control/waittime` | Wait before browser re-login after failures (minutes) |
| `fimer/control/retries` | Consecutive scrape failures before re-login |
| `fimer/control/onoff` | `stop` / `restart` |
| `fimer/status` | Status messages |

The service stays up on scrape errors: it logs/publishes status, retries, and only restarts the browser session after too many consecutive failures.

## systemd install

Template unit: [`fimer.service`](fimer.service).

1. Edit paths and user:

```bash
cp fimer.service /tmp/fimer.service
# replace YOUR_USERNAME and path/to/FimerScraper
sudo cp /tmp/fimer.service /etc/systemd/system/fimer.service
sudo systemctl daemon-reload
sudo systemctl enable --now fimer.service
```

2. Check:

```bash
systemctl status fimer.service
journalctl -u fimer.service -f
```

### Update / deploy from GitHub

On the server (service host):

```bash
cd /path/to/FimerScraper
git pull
sudo systemctl restart fimer.service
```

Dependencies only when `requirements.txt` changed:

```bash
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
sudo systemctl restart fimer.service
```

## Secrets

Never commit `secrets.py`. Use `secrets.example.py` as the template. Keep a secure offline copy — GitHub backs up **code**, not credentials.
