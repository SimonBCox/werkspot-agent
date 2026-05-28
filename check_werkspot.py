import os
import json
import asyncio
import requests
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# ─── Laag 1: snelle trefwoordfilter ─────────────────────────────────
# Vangt duidelijke gevallen op zonder Groq aan te roepen
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
    """Snelle pre-filter. Puur tekenwerk eruit, relevante trefwoorden erin."""
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
    """
    Vraagt Groq (Llama 3) of de opdracht relevant is voor een constructeur
    die zich specialiseert in draagmuurberekeningen en uitbouwberekeningen.
    Wordt alleen aangeroepen voor nieuwe, nog niet geziene opdrachten.
    """
    api_key = os.environ.get('GROQ_API_KEY', '')
    if not api_key:
        print("⚠️  Geen GROQ_API_KEY — alleen trefwoordfilter gebruikt")
        return True  # doorsturen als Groq niet beschikbaar is

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
        return True  # bij fout: liever false positive dan gemiste opdracht

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

# ─── Werkspot scraper ────────────────────────────────────────────────
async def scrape_werkspot(email: str, password: str) -> list[dict]:
    jobs = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage'],
        )
        context = await browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Linux; Android 13; Pixel 7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Mobile Safari/537.36'
            ),
            viewport={'width': 390, 'height': 844},
        )
        page = await context.new_page()

        try:
            print("🔐 Inloggen bij Werkspot...")
            await page.goto('https://www.werkspot.nl/inloggen', wait_until='domcontentloaded', timeout=30_000)
            await page.wait_for_selector('input[type="email"], input[name="email"]', timeout=10_000)
            await page.fill('input[type="email"], input[name="email"]', email)
            await page.fill('input[type="password"], input[name="password"]', password)
            await page.click(
                'button[type="submit"], input[type="submit"], '
                'button:has-text("Inloggen"), button:has-text("Log in")'
            )
            await page.wait_for_load_state('networkidle', timeout=15_000)

            if 'inloggen' in page.url:
                print("❌ Inloggen mislukt")
                await page.screenshot(path='debug_login_failed.png')
                return jobs

            print(f"✅ Ingelogd. URL: {page.url}")

            # Naar leads/opdrachten
            for url_candidate in [
                'https://www.werkspot.nl/pro/leads',
                'https://www.werkspot.nl/pro/opdrachten',
                'https://www.werkspot.nl/vakman/leads',
                'https://www.werkspot.nl/vakman/opdrachten',
            ]:
                await page.goto(url_candidate, wait_until='domcontentloaded', timeout=15_000)
                if 'inloggen' not in page.url and page.url != 'https://www.werkspot.nl/':
                    print(f"✅ Leads-pagina: {page.url}")
                    break

            await page.wait_for_load_state('networkidle', timeout=10_000)
            await asyncio.sleep(2)
            await page.screenshot(path='debug_leads.png', full_page=True)

            print("🔍 Opdrachten ophalen...")
            page_jobs = await page.evaluate('''
                () => {
                    const jobs = [];
                    const seen = new Set();
                    const linkSels = ['a[href*="/lead"]','a[href*="/opdracht"]','a[href*="/klus"]'];
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
                    const cardSels = ['[class*="lead"]','[class*="opdracht"]','[class*="job-card"]','[class*="request-card"]'];
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

    for job in jobs:
        job_id = job.get('id', '').strip()
        if not job_id:
            continue

        new_ids.add(job_id)

        if job_id in seen_ids:
            continue  # al eerder gezien, overslaan

        title = job.get('title', '')
        desc  = job.get('description', '')

        print(f"\n🆕 Nieuwe opdracht: {title[:60]}")

        # Laag 1: trefwoorden
        if not keyword_filter(title, desc):
            print(f"⏭️  Laag 1 filter: niet relevant")
            continue

        # Laag 2: Groq AI
        if not groq_is_relevant(title, desc):
            print(f"⏭️  Groq: niet relevant")
            continue

        # Beide lagen groen → notificatie
        send_notification(ntfy_topic, job)
        notifications += 1

    print(f"\n📬 {notifications} notificatie(s) verstuurd")

    all_ids = list((seen_ids | new_ids))[-1000:]
    with open(seen_file, 'w') as f:
        json.dump(all_ids, f)
    print(f"💾 {len(all_ids)} opdracht-ID's opgeslagen")

if __name__ == '__main__':
    asyncio.run(main())
