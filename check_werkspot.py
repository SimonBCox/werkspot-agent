import os
import json
import asyncio
import requests
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# ─── Laag 1: snelle trefwoordfilter ─────────────────────────────────
RELEVANT_KEYWORDS = [
    'constructieberekening', 'constructie berekening',
    'draagmuur', 'dragende muur', 'dragend',
    'uitbouw', 'aanbouw',
    'doorbraak',
    'constructeur', 'constructief',
    'statische berekening',
    'constructietekening',
    'fundering',
    'dakopbouw', 'optopping',
    'staalconstructie',
]

EXCLUDE_KEYWORDS = [
    'alleen tekenwerk', 'enkel tekenwerk',
    'alleen tekeningen', 'enkel tekeningen',
    'geen berekening',
]

def keyword_filter(title: str, description: str) -> bool:
    text = (title + ' ' + description).lower()
    has_tekening   = 'tekening' in text or 'tekenwerk' in text
    has_berekening = any(k in text for k in ['berekening', 'constructeur', 'constructief', 'constructie'])
    if has_tekening and not has_berekening:
        return False
    for ex in EXCLUDE_KEYWORDS:
        if ex in text:
            return False
    return any(k in text for k in RELEVANT_KEYWORDS)

# ─── Laag 2: Groq AI analyse ─────────────────────────────────────────
def groq_is_relevant(title: str, description: str) -> bool:
    api_key = os.environ.get('GROQ_API_KEY', '')
    if not api_key:
        print("⚠️  Geen GROQ_API_KEY — alleen trefwoordfilter gebruikt")
        return True

    prompt = f"""Je bent een assistent die opdrachten beoordeelt voor een zelfstandig constructeur.
Deze constructeur doet uitsluitend:
- Constructieberekeningen van draagmuren (doorbraken, muren weghalen)
- Constructieberekeningen voor uitbouwen en aanbouwen
- Combinaties van bouwtekeningen + constructieberekeningen

Hij doet NIET:
- Puur tekenwerk zonder berekening
- Verbouwingen of aannemerwerk
- Elektra, loodgieterswerk, schilderwerk etc.

Beoordeel de onderstaande opdracht. Antwoord uitsluitend met JA of NEE.

Titel: {title}
Omschrijving: {description}

Is dit relevant voor deze constructeur?"""

    try:
        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json={
                'model': 'llama-3.1-8b-instant',
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 10,
                'temperature': 0,
            },
            timeout=15,
        )
        response.raise_for_status()
        answer = response.json()['choices'][0]['message']['content'].strip().upper()
        print(f"🤖 Groq zegt: {answer} — {title[:50]}")
        return answer.startswith('JA')
    except Exception as e:
        print(f"⚠️  Groq fout: {e} — doorsturen op basis van trefwoorden")
        return True

# ─── Heartbeat: stille statusmelding elke run ────────────────────────
def send_heartbeat(topic: str, total: int, new: int, notifications: int):
    """Stille melding zodat je weet dat de agent actief is en wat hij ziet."""
    try:
        requests.post(
            f'https://ntfy.sh/{topic}',
            data=f"Gevonden op pagina: {total} | Nieuw: {new} | Notificaties: {notifications}".encode('utf-8'),
            headers={
                'Title':    '🔍 Werkspot scan voltooid',
                'Priority': 'min',    # geen geluid, alleen zichtbaar in notificatiebalk
                'Tags':     'white_check_mark',
            },
            timeout=10,
        )
        print("📡 Heartbeat verstuurd")
    except Exception as e:
        print(f"⚠️  Heartbeat mislukt: {e}")

# ─── Notificatie via ntfy ────────────────────────────────────────────
def send_notification(topic: str, job: dict):
    title = job.get('title', 'Nieuwe opdracht')[:60]
    desc  = job.get('description', '')[:350]
    url   = job.get('url', 'https://www.werkspot.nl/pro/leads')

    try:
        r = requests.post(
            f'https://ntfy.sh/{topic}',
            data=f"{desc}\n\n🔗 {url}".encode('utf-8'),
            headers={
                'Title':    f'🔨 {title}',
                'Priority': 'urgent',
                'Tags':     'triangular_ruler,bell',
                'Click':    url,
                'Sound':    'default',
            },
            timeout=10,
        )
        r.raise_for_status()
        print(f"✅ Notificatie verstuurd: {title}")
    except Exception as e:
        print(f"❌ Notificatie mislukt: {e}")

# ─── Cookie parser ───────────────────────────────────────────────────
def _parse_cookies(raw: str) -> list[dict]:
    """
    Zet een geëxporteerde cookie-JSON (van de 'Cookie-Editor' extensie)
    om naar het formaat dat Playwright verwacht. Slaat ongeldige
    entries over in plaats van de hele lijst te laten falen.
    """
    data = json.loads(raw)
    cookies = []
    for c in data:
        try:
            name = c['name']
            value = c['value']
        except (KeyError, TypeError):
            continue  # geen naam/waarde → overslaan

        cookie = {
            'name':   name,
            'value':  value,
            'domain': c.get('domain', '.werkspot.nl'),
            'path':   c.get('path', '/'),
        }
        if 'expirationDate' in c and c['expirationDate']:
            try:
                cookie['expires'] = int(c['expirationDate'])
            except (ValueError, TypeError):
                pass

        cookie['httpOnly'] = bool(c.get('httpOnly', False))

        # sameSite normaliseren
        ss = str(c.get('sameSite', 'Lax')).lower()
        same_site = {
            'lax': 'Lax', 'strict': 'Strict', 'none': 'None',
            'no_restriction': 'None', 'unspecified': 'Lax',
        }.get(ss, 'Lax')
        cookie['sameSite'] = same_site

        # Chromium-regel: sameSite=None vereist secure=True
        secure = bool(c.get('secure', True))
        if same_site == 'None':
            secure = True
        cookie['secure'] = secure

        cookies.append(cookie)
    return cookies

# ─── Werkspot scraper ────────────────────────────────────────────────
async def scrape_werkspot(email: str, password: str) -> list[dict]:
    jobs = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',  # verberg automatisering
            ],
        )
        context = await browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            ),
            viewport={'width': 1280, 'height': 900},
            locale='nl-NL',
        )

        # Verberg navigator.webdriver zodat we niet als bot herkend worden
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        page = await context.new_page()

        try:
            logged_in = False

            # ════════════════════════════════════════════════════════
            # METHODE 1: Cookie-sessie (aanbevolen, omzeilt de login)
            # ════════════════════════════════════════════════════════
            cookies_raw = os.environ.get('WERKSPOT_COOKIES', '').strip()
            print(f"🍪 WERKSPOT_COOKIES secret: "
                  f"{'GEVONDEN (' + str(len(cookies_raw)) + ' tekens)' if cookies_raw else '❌ LEEG / NIET INGESTELD'}")

            if cookies_raw:
                try:
                    cookies = _parse_cookies(cookies_raw)
                    print(f"   {len(cookies)} cookies geparseerd")

                    # Voeg cookies één voor één toe; sla slechte over zodat
                    # één foute cookie niet de hele batch laat falen.
                    ok, fail = 0, 0
                    for c in cookies:
                        try:
                            await context.add_cookies([c])
                            ok += 1
                        except Exception:
                            fail += 1
                    print(f"   ✅ {ok} cookies toegevoegd, {fail} overgeslagen")

                    # Ga naar de leads-pagina (desktop URL)
                    await page.goto(
                        'https://www.werkspot.nl/service-pro/new-service-requests',
                        wait_until='domcontentloaded',
                        timeout=20_000,
                    )
                    await page.wait_for_load_state('networkidle', timeout=10_000)
                    await asyncio.sleep(2)

                    # Debug: bewaar altijd wat we zien
                    await page.screenshot(path='debug_cookie.png', full_page=True)
                    body = await page.evaluate('() => document.body.innerText')
                    with open('debug_cookie_text.txt', 'w') as f:
                        f.write(body[:4000])
                    print(f"📍 Cookie-pagina URL: {page.url}")

                    # Positieve inlog-signalen: dit menu zie je alleen ingelogd
                    signals = ['Mijn account', 'Uitloggen', 'aangemeld als',
                               'Nieuwe opdrachten', 'Activiteit', 'Contacten']
                    matched = [s for s in signals if s in body]
                    if matched:
                        print(f"✅ Ingelogd via cookies (herkend: {matched})")
                        logged_in = True
                    else:
                        print("⚠️  Geen inlog-signaal gevonden op pagina")
                except Exception as e:
                    print(f"⚠️  Cookie-login mislukt: {e}")

            # ════════════════════════════════════════════════════════
            # METHODE 2: Wachtwoordlogin (fallback)
            # ════════════════════════════════════════════════════════
            if not logged_in:
                print("🔐 Inloggen met e-mail + wachtwoord...")
                await page.goto('https://www.werkspot.nl/inloggen', wait_until='domcontentloaded', timeout=30_000)

                # Cookiebanner wegklikken
                try:
                    await page.wait_for_selector(
                        'button:has-text("Weiger alles"), button:has-text("Accepteer alles")',
                        timeout=5_000
                    )
                    await page.click('button:has-text("Weiger alles")')
                    print("🍪 Cookiebanner gesloten")
                    await page.wait_for_load_state('networkidle', timeout=5_000)
                except Exception:
                    print("ℹ️  Geen cookiebanner gevonden, doorgaan...")

                # Stap 1: e-mail (karakter voor karakter ivm Angular)
                email_loc = page.locator('input[type="email"], input[name="email"]').first
                await email_loc.wait_for(state="visible", timeout=10_000)
                await email_loc.click()
                await email_loc.press_sequentially(email, delay=60)
                await email_loc.press('Tab')
                await asyncio.sleep(1.0)
                print(f"✏️  E-mail getypt: {email}")

                # Diagnostiek: is de bot-vlag verborgen?
                wd = await page.evaluate('() => navigator.webdriver')
                print(f"🤖 navigator.webdriver = {wd} (moet None/False zijn)")

                try:
                    login_btn = page.get_by_role("button", name="Inloggen")
                    await login_btn.wait_for(state="visible", timeout=5_000)
                    disabled = await login_btn.is_disabled()
                    print(f"🔘 Knop disabled? {disabled}")
                    await login_btn.click(timeout=5_000)
                    print("🖱️  Op 'Inloggen' geklikt")
                except Exception as e:
                    print(f"⚠️  Knop klik mislukt ({e}), probeer Enter")
                    await email_loc.press('Enter')

                try:
                    await page.wait_for_selector(
                        'input[type="password"], text="Voer je wachtwoord in", text="Ontvang een code"',
                        timeout=12_000,
                    )
                    print("✅ Volgend scherm geladen")
                except Exception:
                    print("⏳ Volgend scherm niet gedetecteerd")

                await page.screenshot(path='debug_step2.png')
                txt = await page.evaluate('() => document.body.innerText')
                with open('debug_step2_text.txt', 'w') as f:
                    f.write(txt[:3000])
                print(f"📍 Na stap 1: {page.url}")

                # Stap 2: kies wachtwoord-login indien keuzescherm
                try:
                    wachtwoord_optie = page.get_by_text("Voer je wachtwoord in", exact=False)
                    await wachtwoord_optie.wait_for(state="visible", timeout=4_000)
                    await wachtwoord_optie.click()
                    print("🔑 Gekozen voor wachtwoord-login")
                    await page.wait_for_selector('input[type="password"]', timeout=8_000)
                except Exception:
                    print("ℹ️  Geen keuzescherm — direct naar wachtwoord")

                # Stap 3: wachtwoord
                pwd_loc = page.locator('input[type="password"], input[name="password"]').first
                await pwd_loc.wait_for(state="visible", timeout=10_000)
                await pwd_loc.click()
                await pwd_loc.press_sequentially(password, delay=60)
                await pwd_loc.press('Tab')
                await asyncio.sleep(1.0)
                print("✏️  Wachtwoord getypt")

                try:
                    submit_btn = page.get_by_role("button", name="Inloggen")
                    await submit_btn.wait_for(state="visible", timeout=5_000)
                    await submit_btn.click(timeout=5_000)
                    print("🖱️  Op 'Inloggen' geklikt (wachtwoord)")
                except Exception as e:
                    print(f"⚠️  Knop klik mislukt ({e}), probeer Enter")
                    await pwd_loc.press('Enter')

                try:
                    await page.wait_for_function(
                        '() => !window.location.pathname.includes("inloggen")',
                        timeout=15_000,
                    )
                except Exception:
                    pass
                await page.wait_for_load_state('networkidle', timeout=10_000)
                print(f"📍 Na wachtwoord: {page.url}")

                if 'inloggen' in page.url:
                    print("❌ Inloggen mislukt")
                    await page.screenshot(path='debug_login_failed.png')
                    return jobs
                logged_in = True
                print(f"✅ Ingelogd: {page.url}")

            # ── Naar leads (indien nog niet daar) ─────────────────
            if 'new-service-requests' not in page.url:
                for url_candidate in [
                    'https://www.werkspot.nl/service-pro/new-service-requests',
                    'https://www.werkspot.nl/service-pro/service-requests',
                ]:
                    await page.goto(url_candidate, wait_until='domcontentloaded', timeout=15_000)
                    body = await page.evaluate('() => document.body.innerText')
                    if 'inloggen' not in page.url and 'kunnen deze pagina niet vinden' not in body:
                        print(f"✅ Leads-pagina gevonden: {page.url}")
                        break

            await page.wait_for_load_state('networkidle', timeout=10_000)
            await asyncio.sleep(2)

            # Sla altijd een screenshot op zodat je kunt zien wat de scraper ziet
            await page.screenshot(path='debug_leads.png', full_page=True)
            print("📸 Screenshot opgeslagen als debug_leads.png")

            # Dump volledige paginatekst voor debug
            page_text = await page.evaluate('() => document.body.innerText')
            with open('debug_page_text.txt', 'w') as f:
                f.write(page_text[:5000])  # eerste 5000 tekens
            print("📄 Paginatekst opgeslagen als debug_page_text.txt (eerste 5000 tekens):")
            print("─" * 60)
            print(page_text[:1000])
            print("─" * 60)

            print("🔍 Opdrachten ophalen...")
            page_jobs = await page.evaluate('''
                () => {
                    const jobs = [];
                    const seen = new Set();
                    const linkSels = ['a[href*="/service-request"]','a[href*="/lead"]','a[href*="/opdracht"]','a[href*="/klus"]'];
                    for (const sel of linkSels) {
                        document.querySelectorAll(sel).forEach(el => {
                            if (seen.has(el.href)) return;
                            seen.add(el.href);
                            const container = el.closest('li, article, [class*="card"], [class*="item"], [class*="lead"]') || el.parentElement;
                            const text  = (container || el).innerText || '';
                            const lines = text.split('\\n').map(l => l.trim()).filter(Boolean);
                            jobs.push({
                                id:          el.href,
                                title:       lines[0] || el.innerText.trim() || el.href,
                                description: lines.slice(1).join(' ').substring(0, 500),
                                url:         el.href,
                            });
                        });
                    }
                    const cardSels = ['[class*="service-request"]','[class*="request"]','[class*="lead"]','[class*="opdracht"]','[class*="job-card"]','[class*="request-card"]'];
                    for (const sel of cardSels) {
                        document.querySelectorAll(sel).forEach(el => {
                            const link = el.querySelector('a');
                            const href = link ? link.href : el.getAttribute('data-url') || '';
                            if (!href || seen.has(href)) return;
                            seen.add(href);
                            const text  = el.innerText || '';
                            const lines = text.split('\\n').map(l => l.trim()).filter(Boolean);
                            jobs.push({ id: href, title: lines[0] || 'Opdracht', description: lines.slice(1).join(' ').substring(0, 500), url: href });
                        });
                    }
                    return jobs;
                }
            ''')

            print(f"📊 {len(page_jobs)} opdrachten gevonden op de pagina")

            # Print alle gevonden opdrachten zodat je kunt controleren wat er gevonden wordt
            for i, job in enumerate(page_jobs):
                print(f"  [{i+1}] {job.get('title','?')[:70]}")
                print(f"       {job.get('url','')[:80]}")

            jobs = page_jobs

        except PlaywrightTimeout as e:
            print(f"⏱️ Timeout: {e}")
            await page.screenshot(path='debug_timeout.png')
        except Exception as e:
            print(f"❌ Fout: {e}")
            await page.screenshot(path='debug_error.png')
        finally:
            await browser.close()

    return jobs

# ─── Hoofdprogramma ──────────────────────────────────────────────────
async def main():
    seen_file = 'seen_jobs.json'
    seen_ids: set[str] = set()
    if os.path.exists(seen_file):
        with open(seen_file) as f:
            seen_ids = set(json.load(f))
    print(f"📚 {len(seen_ids)} eerder geziene opdrachten geladen")

    email      = os.environ['WERKSPOT_EMAIL']
    password   = os.environ['WERKSPOT_PASSWORD']
    ntfy_topic = os.environ['NTFY_TOPIC']

    jobs = await scrape_werkspot(email, password)

    new_ids       = set()
    notifications = 0
    new_count     = 0

    for job in jobs:
        job_id = job.get('id', '').strip()
        if not job_id:
            continue

        new_ids.add(job_id)

        if job_id in seen_ids:
            continue

        new_count += 1
        title = job.get('title', '')
        desc  = job.get('description', '')

        print(f"\n🆕 Nieuwe opdracht: {title[:60]}")

        if not keyword_filter(title, desc):
            print(f"   ⏭️  Laag 1 filter: niet relevant")
            continue

        if not groq_is_relevant(title, desc):
            print(f"   ⏭️  Groq: niet relevant")
            continue

        send_notification(ntfy_topic, job)
        notifications += 1

    print(f"\n{'='*50}")
    print(f"📊 Totaal op pagina : {len(jobs)}")
    print(f"🆕 Nieuw deze run   : {new_count}")
    print(f"📬 Notificaties     : {notifications}")
    print(f"{'='*50}")

    # Stille heartbeat zodat je in ntfy kunt zien dat de agent actief is
    send_heartbeat(ntfy_topic, total=len(jobs), new=new_count, notifications=notifications)

    all_ids = list((seen_ids | new_ids))[-1000:]
    with open(seen_file, 'w') as f:
        json.dump(all_ids, f)
    print(f"💾 {len(all_ids)} opdracht-ID's opgeslagen")

if __name__ == '__main__':
    asyncio.run(main())
