# Kopie vom StScraper - angepasst für Fimer-Abfrage
# Stand 09.07.2023: Anmelden klappt nicht - Login-Button lässt sich nicht auslösen...
# Stand 24.05.2024: Versuch, mit ChatGPT alles hinzukriegen... (https://chatgpt.com/share/fe895b83-7695-479d-bcc5-c6d2a114746b)
#   - erster Test mit Playwright in separatem File playwright-login.py
#   - Danach hier zusammengebastelt und gleich durch ChatGPT neu schreiben lassen :-)
# Stand 26.07.2026: Überarbeitet mit Cursor und Grok 4.5

import asyncio
import datetime
import json
import socket
import sys

import paho.mqtt.client as mqtt
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

import secrets

control = {
    "onoff": "",
    "delay": 30,
    "waittime": 15,
    "retries": 3,
}

host = socket.gethostname()

# Home Assistant MQTT device discovery (one device, several sensors).
HA_DISCOVERY_TOPIC = "homeassistant/device/fimer/config"
HA_DEVICE = {
    "identifiers": ["fimer"],
    "name": "Fimer",
    "manufacturer": "Fimer",
    "model": "Inverter",
}


def ha_discovery_payload():
    """Build retained discovery payload so HA creates a single Fimer device."""
    return {
        "device": HA_DEVICE,
        "origin": {
            "name": "FimerScraper",
            "sw": "1.0",
        },
        "components": {
            "status": {
                "platform": "sensor",
                "name": "Status",
                "unique_id": "fimer_status",
                "state_topic": "fimer/status",
                "entity_category": "diagnostic",
                "icon": "mdi:solar-power",
            },
            "updated": {
                "platform": "sensor",
                "name": "Updated",
                "unique_id": "fimer_updated",
                "state_topic": "fimer/Time",
                "entity_category": "diagnostic",
                "icon": "mdi:clock-outline",
            },
            "p1": {
                "platform": "sensor",
                "name": "MPPT1 Power",
                "unique_id": "fimer_p1",
                "state_topic": "fimer/P1",
                "device_class": "power",
                "state_class": "measurement",
                "unit_of_measurement": "kW",
            },
            "p2": {
                "platform": "sensor",
                "name": "MPPT2 Power",
                "unique_id": "fimer_p2",
                "state_topic": "fimer/P2",
                "device_class": "power",
                "state_class": "measurement",
                "unit_of_measurement": "kW",
            },
            "p3": {
                "platform": "sensor",
                "name": "MPPT3 Power",
                "unique_id": "fimer_p3",
                "state_topic": "fimer/P3",
                "device_class": "power",
                "state_class": "measurement",
                "unit_of_measurement": "kW",
            },
            "p4": {
                "platform": "sensor",
                "name": "MPPT4 Power",
                "unique_id": "fimer_p4",
                "state_topic": "fimer/P4",
                "device_class": "power",
                "state_class": "measurement",
                "unit_of_measurement": "kW",
            },
            "derating": {
                "platform": "sensor",
                "name": "Derating",
                "unique_id": "fimer_derating",
                "state_topic": "fimer/Derating",
                "icon": "mdi:tune-vertical",
            },
        },
    }


def publish_ha_discovery(client):
    payload = json.dumps(ha_discovery_payload())
    client.publish(HA_DISCOVERY_TOPIC, payload=payload, retain=True)
    print(f"HA discovery published to {HA_DISCOVERY_TOPIC}", flush=True)


def on_connect(client, userdata, flags, reason_code, properties):
    print(f"MQTT connected with result code {reason_code}", flush=True)
    client.subscribe("fimer/control/#")
    publish_ha_discovery(client)


def on_message(client, userdata, msg):
    received = str(msg.payload.decode("utf-8"))
    print(f"{msg.topic} {received}", flush=True)
    if msg.topic == "fimer/control/onoff":
        control["onoff"] = received
    elif msg.topic == "fimer/control/delay":
        control["delay"] = received
    elif msg.topic == "fimer/control/waittime":
        control["waittime"] = received
    elif msg.topic == "fimer/control/retries":
        control["retries"] = received


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.username_pw_set(secrets.mqtt_user, password=secrets.mqtt_pwd)
client.connect(secrets.mqtt_host, secrets.mqtt_port, 60)
client.loop_start()

client.publish(
    "fimer/status",
    payload=f'Fimer-Scraper gestartet auf {host}, Abrufintervall (delay): {control["delay"]}s',
)


async def login_and_get_page(browser):
    context = await browser.new_context()
    page = await context.new_page()
    await page.goto(secrets.portal_loginpath)
    await page.wait_for_selector("#login-btn")
    await page.click("#login-btn")
    return page


async def extract_data(page):
    data = {
        "P1": await page.text_content("#mppt__1_power-value"),
        "P2": await page.text_content("#mppt__2_power-value"),
        "P3": await page.text_content("#mppt__3_power-value"),
        "P4": await page.text_content("#mppt__4_power-value"),
        # Derating: State "power_curtailment" or "Kein Derating".
        "Derating": (
            await page.text_content(
                "#derating_monitor_obj_grid_active_power_derating_src-value"
            )
            or ""
        ).strip(),
    }
    return data


def publish_data(data, loop_count):
    now = datetime.datetime.now()
    data["Timestamp"] = now
    data["Date"] = now.strftime("%d.%m.%Y")
    data["Time"] = now.strftime("%H:%M:%S")
    for key, value in data.items():
        client.publish("fimer/" + key, payload=str(value).replace(",", "."))
        print(f"{key:16}{value}", flush=True)
    client.publish(
        "fimer/status",
        payload=f'Loop {loop_count}, {len(data)} items sent from {host}, delay={control["delay"]}s',
    )
    print(f'Loop {loop_count} OK, {len(data)} items, delay={control["delay"]}s', flush=True)


async def scrape_session():
    """Run one browser session until stop/restart or too many consecutive failures."""
    consecutive_failures = 0
    max_failures = max(1, int(control["retries"]))

    async with async_playwright() as p:
        client.publish("fimer/status", payload="Anmeldung starten.")
        browser = await p.chromium.launch(headless=True)
        try:
            page = await login_and_get_page(browser)
            client.publish("fimer/status", payload="Anmeldung erfolgreich.")
            loop_count = 0

            while control["onoff"] != "stop":
                if control["onoff"] == "restart":
                    control["onoff"] = ""
                    client.publish("fimer/status", payload="Neustart angefordert...")
                    return "restart"

                if loop_count > 0:
                    await asyncio.sleep(int(control["delay"]))
                else:
                    client.publish("fimer/status", payload="Abfrage gestartet")

                loop_count += 1
                try:
                    data = await extract_data(page)
                    publish_data(data, loop_count)
                    consecutive_failures = 0
                except PlaywrightTimeoutError as e:
                    consecutive_failures += 1
                    msg = (
                        f"Timeout beim Abruf (Fehler {consecutive_failures}/{max_failures}): {e}"
                    )
                    print(msg, flush=True)
                    client.publish("fimer/status", payload=msg)
                except Exception as e:
                    consecutive_failures += 1
                    msg = (
                        f"Fehler beim Abruf (Fehler {consecutive_failures}/{max_failures}): {e}"
                    )
                    print(msg, flush=True)
                    client.publish("fimer/status", payload=msg)

                if consecutive_failures >= max_failures:
                    client.publish(
                        "fimer/status",
                        payload="Zu viele Fehler in Folge — Browser-Session wird neu gestartet.",
                    )
                    return "retry"
        finally:
            try:
                await browser.close()
            except Exception as e:
                print(f"Fehler: Chromium konnte nicht beendet werden: {e}", flush=True)
                client.publish(
                    "fimer/status",
                    payload=f"Fehler: Chromium konnte nicht beendet werden: {e}",
                )

    return "stop" if control["onoff"] == "stop" else "retry"


async def main():
    session = 0
    while control["onoff"] != "stop":
        if session > 0:
            wait_min = float(control["waittime"])
            # Short backoff for the first few reconnects, then use waittime.
            if session == 1:
                wait_min = min(wait_min, 0.2)
            elif session < 4:
                wait_min = min(wait_min, 3)
            client.publish(
                "fimer/status",
                payload=f"Warte {wait_min} min vor Session-Neustart ({session})...",
            )
            await asyncio.sleep(wait_min * 60)

        session += 1
        try:
            result = await scrape_session()
        except KeyboardInterrupt:
            client.publish("fimer/status", payload="Abruf manuell abgebrochen")
            break
        except Exception as e:
            print(f"Session-Fehler: {e}", flush=True)
            client.publish("fimer/status", payload=f"Session-Fehler: {e}")
            continue

        if result == "stop":
            break
        if result == "restart":
            session = 0
            continue
        # result == "retry": keep looping with backoff

    print("Abruf fimer-Heizkreisdaten wurde beendet.", flush=True)
    client.publish(
        "fimer/status",
        payload=f"Notify: Abruf fimer-Heizkreisdaten von {host} wurde beendet.",
    )
    client.loop_stop()


if __name__ == "__main__":
    asyncio.run(main())
