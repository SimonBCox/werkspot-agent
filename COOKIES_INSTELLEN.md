# Cookie-sessie instellen (aanbevolen)

De geautomatiseerde login werkt vaak niet omdat Werkspot bots blokkeert. De
oplossing: log één keer handmatig in en geef de agent jouw sessie mee. Werkspot
sessies blijven meestal weken geldig.

---

## Stap 1 — Installeer de Cookie-Editor extensie

Op je **computer** (niet telefoon), in Chrome of Firefox:
- Chrome: zoek in de Chrome Web Store op **"Cookie-Editor"** → toevoegen
- Firefox: zoek op addons.mozilla.org op **"Cookie-Editor"** → toevoegen

## Stap 2 — Log in op Werkspot

1. Ga naar **werkspot.nl** en log normaal in met je e-mail en wachtwoord
2. Zorg dat je echt ingelogd bent (je ziet je eigen account/opdrachten)

## Stap 3 — Exporteer je cookies

1. Klik op het **Cookie-Editor icoontje** (rechtsboven in je browser)
2. Klik onderin op **Export** (icoon met pijl omhoog)
3. Kies **Export as JSON** → de cookies staan nu op je klembord
   (of er verschijnt een tekstveld — selecteer en kopieer alles)

## Stap 4 — Plak als GitHub Secret

1. Ga naar je repo → **Settings → Secrets and variables → Actions**
2. Klik **New repository secret**
3. Naam: `WERKSPOT_COOKIES`
4. Value: plak de hele JSON die je net gekopieerd hebt
5. **Add secret**

## Stap 5 — Test

Ga naar **Actions → Check Werkspot Leads → Run workflow**.
In de logs zie je nu:
```
🍪 Cookie-sessie laden...
   42 cookies geladen
✅ Ingelogd via cookies: https://www.werkspot.nl/pro/leads
```

---

## Cookies verlopen

Na een paar weken kan de sessie verlopen. Je merkt dit aan de melding:
```
⚠️ Cookies verlopen of ongeldig
```
Herhaal dan stap 2 t/m 4 om de cookies te vernieuwen.

> De agent valt automatisch terug op e-mail+wachtwoord login als de cookies
> ontbreken of verlopen zijn — maar die login wordt vaak geblokkeerd, dus
> cookies zijn de betrouwbare route.
