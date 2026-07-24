# Kopie vom StScraper - angepasst für Fimer-Abfrage
# Stand 09.07.2023: Anmelden klappt nicht - Login-Button lässt sich nicht auslösen...
# Stand 24.05.2024: Versuch, mit ChatGPT alles hinzukriegen... (https://chatgpt.com/share/fe895b83-7695-479d-bcc5-c6d2a114746b)
#   - erster Test mit Playwright in separatem File playwright-login.py
#   - Danach hier zusammengebastelt und gleich durch ChatGPT neu schreiben lassen :-)

import datetime
import sys
import socket
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import asyncio
import paho.mqtt.client as mqtt
import secrets


# MQTT setup and callbacks
def on_connect(client, userdata, flags, rc):
    print("MQTT connected with result code " + str(rc))
    client.subscribe("fimer/control/#")


def on_message(client, userdata, msg):
    received = str(msg.payload.decode("utf-8"))
    print(msg.topic + " " + received)
    if msg.topic == "fimer/control/onoff":
        control['onoff'] = received
    if msg.topic == "fimer/control/delay":
        control['delay'] = received

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.username_pw_set(secrets.mqtt_user, password=secrets.mqtt_pwd)
client.connect(secrets.mqtt_host, secrets.mqtt_port, 60)
client.loop_start()

control = {
    'onoff': '',
    'delay': 30,
    'waittime': 15,
    'retries': 1
}

host = socket.gethostname()
client.publish('fimer/status', payload=f'Fimer-Scraper gestartet auf {host}, Abrufintervall (delay): {control["delay"]}s')

# Function to perform login and return the page object
async def login_and_get_page(browser):
    context = await browser.new_context()
    page = await context.new_page()
    await page.goto(secrets.portal_loginpath)

    # Wait for the login button to be visible and click it
    await page.wait_for_selector('#login-btn')
    await page.click('#login-btn')

    return page

# Function to extract data
async def extract_data(page):
    data = {}
    data["P1"] = await page.text_content('#mppt__1_power-value')
    data["P2"] = await page.text_content('#mppt__2_power-value')
    data["P3"] = await page.text_content('#mppt__3_power-value')
    data["P4"] = await page.text_content('#mppt__4_power-value')
    # Derating: State "power_curtailment" or "Kein Derating". Unknown where to get the value from.
    data["Derating"] = (await page.text_content('#derating_monitor_obj_grid_active_power_derating_src-value') or "").strip()
    return data

# Main function to control the scraping and MQTT publishing
async def main():
    abrufversuche = 0

    while abrufversuche < int(control['retries']):
        if abrufversuche > 0:
            wartezeit = 0.2 if abrufversuche == 1 else (3 if abrufversuche < 4 else int(control['waittime']))
            client.publish('fimer/status', payload=f'Abrufversuch {abrufversuche}: Warte {wartezeit} min ...')
            await asyncio.sleep(wartezeit * 60)

        abrufversuche += 1

        async with async_playwright() as p:
            client.publish('fimer/status', payload=f'Anmeldung starten.')
            browser = await p.chromium.launch(headless=True)

            try:
                page = await login_and_get_page(browser)
                client.publish('fimer/status', payload=f'Anmeldung erfolgreich.')
                x = 0

                while control['onoff'] != "stop":
                    if control['onoff'] == "restart":
                        control['onoff'] = ""
                        raise InterruptedError('Neustart angefordert...')

                    if x > 0:
                        await asyncio.sleep(int(control['delay']))
                    else:
                        client.publish('fimer/status', payload='Abfrage gestartet')
                    x += 1

                    data = await extract_data(page)

                    data["Timestamp"] = datetime.datetime.now()
                    data["Date"] = datetime.datetime.now().strftime("%d.%m.%Y")
                    data["Time"] = datetime.datetime.now().strftime("%H:%M:%S")

                    for key in data:
                        client.publish('fimer/' + key, payload=str(data[key]).replace(',', '.'))
                        print(f'{key:16}{data[key]}')
                    client.publish('fimer/status', payload=f'Loop {x}, {len(data)} items sent from {host}, delay={control["delay"]}s')
                    print(f'Loop {x} OK, {len(data)} items, delay={control["delay"]}s')
                    abrufversuche = 0

                break  # Exit the loop if the scraping is successful

            except KeyboardInterrupt:
                client.publish('fimer/status', payload=f'Abruf der fimer-Heizkreisdaten manuell abgebrochen')
                sys.exit(0)

            except PlaywrightTimeoutError:
                print(f'Fehler: Timeout beim Abruf der Daten (Versuch {abrufversuche})')
                client.publish('fimer/status', payload=f'Fehler: Timeout beim Abruf der Daten (Versuch {abrufversuche})')

            except Exception as e:
                print(f'Fehler beim Abruf der fimer-Heizkreisdaten (Versuch {abrufversuche}): {e}')
                client.publish('fimer/status', payload=f'Fehler beim Abruf der fimer-Heizkreisdaten (Versuch {abrufversuche}): {e}')

            finally:
                try:
                    await browser.close()
                except Exception as e:
                    print(f'Fehler: Chromium konnte nicht beendet werden: {e}')
                    client.publish('fimer/status', payload=f'Fehler: Chromium konnte nicht beendet werden: {e}')

    print('Abruf fimer-Heizkreisdaten wurde beendet.')
    client.publish('fimer/status', payload=f'Notify: Abruf fimer-Heizkreisdaten von {host} wurde beendet.')
    client.loop_stop()

if __name__ == "__main__":
    asyncio.run(main())
