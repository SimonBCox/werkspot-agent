# Werkspot Lead Checker 🔨
 
Controleert elke 15 minuten Werkspot op nieuwe relevante opdrachten en stuurt een pushmelding naar je telefoon via **ntfy**.

---

## Installatie (±10 minuten)

### Stap 1 – Maak een nieuw GitHub repo aan

1. Ga naar [github.com/new](https://github.com/new)
2. Naam: `werkspot-agent`
3. Zet op **Public** (gratis GitHub Actions minuten zijn onbeperkt voor publieke repos)
4. Klik **Create repository**

### Stap 2 – Upload de bestanden

Upload deze 4 bestanden naar het root van je repo:
- `check_werkspot.py`
- `seen_jobs.json`
- `.github/workflows/check_werkspot.yml`

> Tip: je kunt bestanden direct uploaden via de GitHub website (Add file → Upload files).
> De map `.github/workflows/` moet je aanmaken via "Create new file" en dan het pad typen.

### Stap 3 – Installeer ntfy op je Android

1. Download **ntfy** uit de Play Store (gratis, geen account nodig)
2. Kies een unieke naam voor jouw kanaal, bijv. `werkspot-simon-2024` (mag niet door anderen al in gebruik zijn)
3. Open ntfy → tik op **+** → voer jouw kanaalnaam in → Subscribe
4. Zorg dat notificaties aan staan voor ntfy en zet het geluid op max

### Stap 4 – Sla je gegevens veilig op in GitHub Secrets

1. Ga in je repo naar **Settings → Secrets and variables → Actions**
2. Voeg deze 3 secrets toe via **New repository secret**:

| Naam | Waarde |
|------|--------|
| `WERKSPOT_EMAIL` | jouw Werkspot e-mailadres |
| `WERKSPOT_PASSWORD` | jouw Werkspot wachtwoord |
| `NTFY_TOPIC` | jouw gekozen kanaalnaam (bijv. `werkspot-simon-2024`) |

> Je wachtwoord is versleuteld opgeslagen en nooit zichtbaar, ook niet in de logs.

### Stap 5 – Test het handmatig

1. Ga naar **Actions** tab in je repo
2. Klik op **Check Werkspot Leads**
3. Klik rechts op **Run workflow → Run workflow**
4. Bekijk de logs – je ziet wat er gevonden wordt
5. Als er iets misgaat: download de debug screenshots onder **Artifacts**

---

## Hoe werkt het?

```
Elke 15 minuten:
  GitHub start een mini-computer
  → Opent werkspot.nl (automatisch ingelogd)
  → Scant nieuwe opdrachten
  → Relevant? → pushmelding op jouw telefoon 🔔
  → Mini-computer gaat weer uit
```

## Relevantiefilter

De agent stuurt alleen meldingen voor opdrachten met trefwoorden zoals:
- constructieberekening, draagmuur, dragende muur
- uitbouw, aanbouw, doorbraak
- constructeur, statische berekening, fundering

Puur tekenwerk (zonder berekening) wordt **automatisch gefilterd**.

Wil je trefwoorden aanpassen? Bewerk `RELEVANT_KEYWORDS` in `check_werkspot.py`.

---

## Problemen?

- **Geen meldingen?** → Run handmatig en check de logs onder Actions
- **Login mislukt?** → Download debug screenshot via Artifacts
- **Verkeerde opdrachten?** → Pas `RELEVANT_KEYWORDS` aan in het script

---

## Later: automatisch reageren

Zodra de notificaties goed werken kan de agent uitgebreid worden om ook automatisch op opdrachten te reageren met een standaard introductietekst. Dat is stap 2.
