# SugarWOD Coach – Home-Assistant-Add-on

Wertet deine CrossFit-Workouts aus [SugarWOD](https://www.sugarwod.com) aus und läuft als eigener
Container in Home Assistant, mit Weboberfläche in der Seitenleiste.

- **Gewichtsvorschlag**: geschätztes 1RM pro Übung (Epley/Brzycki) und daraus ein Arbeitsgewicht
  für Kraftteile (Sätze × Wdh. + Intensität), Prozentvorgaben und Metcons. Die Rechnung wird offen
  angezeigt.
- **Verlauf**: Diagramm pro Übung mit schwerstem Satz, geschätztem 1RM und markierten Bestwerten.
- **Stärken & Schwächen**: Kraftverhältnisse gegen Richtwerte (z. B. Front/Back Squat,
  Snatch/Clean & Jerk, Push/Strict Press), Trends (steigend, stagnierend, fallend),
  Trainingsbalance über Squat, Zug, Drücken, Gewichtheben, Gymnastics, Engine sowie wiederholte
  Benchmarks wie Fran. Daraus entsteht eine Liste, woran du arbeiten solltest.
- **Home-Assistant-Sensoren**: `sensor.sugarwod_<übung>_1rm` für die Hauptübungen,
  `sensor.sugarwod_letztes_training` und `sensor.sugarwod_trainingstage_30_tage`.

## Daten aus SugarWOD holen

SugarWOD hat keine öffentliche Schnittstelle für Athleten. Die offizielle API gibt es nur für Boxen.
Deshalb nutzt das Add-on den CSV-Export:

1. SugarWOD-App → **More** → **Tools & Resources** → **Export Workouts**.
2. Die CSV kommt per Mail.
3. In der Add-on-Oberfläche unter **Import** hochladen, oder die Datei in den Ordner
   `/share/sugarwod` legen (z. B. per Samba-Freigabe „share“). Der Ordner wird jede Minute geprüft;
   importierte Dateien landen in `importiert/`, unlesbare in `fehlerhaft/`.

Du kannst immer den kompletten Export erneut hochladen: bereits bekannte Einträge werden übersprungen.

> **Einheiten:** SugarWOD exportiert Gewichte in der Regel in **lbs**, auch wenn deine Box in kg
> protokolliert. Stimmen die Werte nach dem Import nicht (z. B. Back Squat 300 kg), stell
> „Einheit im SugarWOD-Export“ um, lösche die Daten unter Import und importiere erneut.

## Installation (GitHub-Repository)

1. Dieses Repository auf GitHub veröffentlichen und in `repository.yaml` sowie
   `sugarwod_coach/config.yaml` die URL (`OWNER`) anpassen.
2. In Home Assistant: **Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories**, die
   GitHub-URL eintragen.
3. **SugarWOD Coach** installieren, starten und „In Seitenleiste anzeigen“ aktivieren.

Home Assistant baut das Image beim Installieren selbst (amd64 und aarch64). Das dauert beim ersten
Mal ein paar Minuten.

## Optionen

| Option | Bedeutung |
| --- | --- |
| `export_unit` | Einheit der Gewichte im SugarWOD-Export (`lbs` oder `kg`) |
| `display_unit` | Einheit für Oberfläche und Sensoren |
| `plate_increment` | Rundung der Vorschläge, in der Anzeigeeinheit (Standard 2,5) |
| `formula` | `epley`, `brzycki` oder `mittel` |
| `body_weight_kg` | Optional, für relative Kraft (× Körpergewicht). 0 = aus |
| `ha_sensors` | Sensoren an Home Assistant melden |
| `sensor_lifts` | Übungen, für die ein 1RM-Sensor angelegt wird |
| `watch_folder` | Ordner für den automatischen Import |

## So rechnet das Add-on

- **Geschätztes 1RM** pro Satz: Epley `G × (1 + W/30)`, Brzycki `G × 36 / (37 − W)` oder der
  Mittelwert. Sätze mit mehr als 12 Wiederholungen werden wie 12 gezählt. Fehlversuche zählen nicht.
- **Aktuelles 1RM** = bestes geschätztes 1RM der letzten 180 Tage, sonst der ältere Bestwert
  (dann ausgegraut).
- **Wiederholungen** stehen im Export nicht immer pro Satz. Sie werden aus Titel und Beschreibung
  gelesen (`5x5`, `5-5-3-3-1`, `3RM`, „heavy single“). Ohne Angabe wird 1 Wiederholung angenommen,
  und die Oberfläche sagt das dazu.
- **Kraftteil-Vorschlag**: Gewicht, das du für *Wdh. + Reserve* bis zum Versagen schaffen würdest
  (Technik 4, moderat 2, schwer 1, maximal 0 Wdh. Reserve), ab 4 Sätzen 2,5 % weniger.
- **Metcon-Vorschlag**: Prozentband vom 1RM je Wiederholungen pro Runde (z. B. 4–6 Wdh. → 60–72 %).
- **Trend**: bestes 1RM der letzten 90 Tage gegen die 90 Tage davor (≥ +2 % steigend,
  ≤ −3 % fallend, dazwischen stagnierend).

Alle Werte sind Schätzungen. Tagesform, Technik und die Vorgaben deines Coaches gehen vor.

## Lokal entwickeln

```bash
python3 -m venv .venv && .venv/bin/pip install -r sugarwod_coach/requirements.txt
```

```bash
.venv/bin/python -m unittest discover tests
```

```bash
cd sugarwod_coach/app && DATA_DIR=../../.localdata PORT=8099 ../../.venv/bin/python -m server
```

Danach <http://localhost:8099> öffnen und `sample_data/sugarwod_beispiel.csv` importieren. Die
Beispieldaten sind erfunden (`sample_data/generate.py`) und enthalten absichtlich Schwächen,
z. B. einen schwachen Snatch.

## Aufbau

```
repository.yaml              Add-on-Repository für Home Assistant
sugarwod_coach/
  config.yaml, build.yaml    Add-on-Definition, Basis-Images
  Dockerfile, run.sh         Container
  app/server.py              Flask/Waitress-Server (Ingress, Port 8099), Ordner-Import, Sensor-Schleife
  app/importer.py            CSV-Import nach SQLite (/data/sugarwod.db)
  app/analysis.py            1RM, Vorschläge, Verhältnisse, Trends, Empfehlungen
  app/ha.py                  Sensoren über http://supervisor/core/api
  app/static/                Oberfläche (Chart.js lokal eingebunden)
tests/                       Unit-Tests
sample_data/                 Beispiel-Export
```
