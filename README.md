# Ernährungs- und Bewegungstracker

Lokal laufende Anwendung zur Erfassung von Mahlzeiten, Tagesaktivität, Sport und Gewicht,
umgesetzt mit **Python**, **Streamlit** und **SQLite**.

Keine Cloud, keine Nutzerkonten, keine Netzverbindung erforderlich. Alle Daten stehen in
einer einzigen Datei `tracker.db` im Projektordner. Nährwertquelle ist der
Bundeslebensmittelschlüssel 4.0 des Max Rubner-Instituts, die MET-Werte stammen aus dem
Compendium of Physical Activities 2024.

## Was die Anwendung besonders macht

Der Tagesbedarf wird **aus dem tatsächlichen Tagesablauf** berechnet, nicht über einen
einmalig gewählten Aktivitätsfaktor. Der Tag hat 1440 Minuten und wird vollständig in vier
Blöcke aufgeteilt:

| Block | Erfassung |
|---|---|
| Schlaf | in Stunden und Minuten |
| Arbeit, nach Haltung getrennt (sitzend, stehend, Veranstaltung) | in Stunden, Vorlage je Tagestyp |
| Sport, je Einheit | Kategorie, Intensität, Dauer in Minuten |
| Restzeit | **nicht erfasst**, sondern berechnet: 1440 − Schlaf − Arbeit − Sport |

Jeder Block geht mit seinem eigenen MET-Wert ein: `(MET − 1) × Gewicht in kg × Stunden`.
Der Abzug von 1 MET ist zwingend, weil der Ruheumsatz bereits im Grundumsatz steckt.

Dadurch verdrängt Arbeitszeit die Restzeit, statt zusätzlich zu ihr zu zählen: Ein Bürotag
mit vier Stunden Stehen ergibt einen anderen Bedarf als ein Homeoffice-Tag mit einer
Stunde Stehen, obwohl beide acht Stunden Arbeit haben. Ergeben die erfassten Zeiten
zusammen mehr als 24 Stunden, wird **kein** Bedarf ausgegeben, sondern ein Hinweis.

## Voraussetzungen

- Python 3.10 oder neuer
- Die Quelldateien des Bundeslebensmittelschlüssels (siehe [Datenquellen](#datenquellen-und-lizenz)) —
  sie liegen **nicht** im Repository

## Einrichtung

**1. Virtuelle Umgebung anlegen und aktivieren**

```bash
python -m venv .venv
```

```bash
.venv\Scripts\activate
```

Unter Linux oder macOS stattdessen `source .venv/bin/activate`.

**2. Abhängigkeiten installieren**

```bash
pip install -r requirements.txt
```

```bash
pip install openpyxl
```

`openpyxl` wird nur vom einmaligen BLS-Import gebraucht und steht deshalb nicht in
`requirements.txt`; die Anwendung selbst braucht es nicht.

**3. BLS-Datei bereitlegen**

Die Datei `BLS_4_0_Daten_2025_DE.xlsx` gehört unverändert in den Ordner `quellen/`. Er ist
von der Versionsverwaltung ausgenommen, weil die Quelldateien groß sind und nicht zum
Projekt gehören.

**4. Stammdaten importieren** (einmalig, in dieser Reihenfolge, aus dem Projektordner)

```bash
python importe/import_bls.py
```

```bash
python importe/import_sportarten.py
```

```bash
python importe/import_met_grundwerte.py
```

```bash
python importe/import_referenzwerte.py
```

Der erste Lauf legt `tracker.db` an und füllt sie mit 7140 Lebensmitteln und rund 57 000
Nährwerten; das dauert etwa eine Minute. Die beiden anderen Skripte lesen
`daten/sportarten.csv` und `daten/met_grundwerte.csv`, die im Repository liegen.

Jedes Skript meldet am Ende, was es geschrieben hat. Ein zweiter Lauf erzeugt keine
Duplikate: die Importe für Sportarten und MET-Grundwerte aktualisieren vorhandene
Einträge, `import_bls.py` verlangt dafür ausdrücklich `--ersetzen` und aktualisiert dann
anhand des BLS-Schlüssels, ohne Kennungen zu ändern — bereits erfasste Mahlzeiten bleiben
gültig.

**5. Anwendung starten**

```bash
streamlit run app.py
```

Der Browser öffnet sich auf http://localhost:8501. Das Terminalfenster muss offen bleiben,
**Strg+C** beendet die Anwendung.

## Aufbau

```
ernaehrungstracker/
├── app.py                          Einstieg: Profilwahl, Navigation über sieben Seiten
├── src/
│   ├── berechnung.py               Alter, Grundumsatz, Tagesblöcke, Kalorienziel, Summen
│   ├── datenbank.py                Schema und sämtliche Datenzugriffe
│   ├── export.py                   CSV-Dateien und ZIP des Datenexports
│   └── seiten/                     je eine Datei pro Seite
│       ├── profil.py
│       ├── mahlzeiten.py
│       ├── lebensmittel.py
│       ├── aktivitaet.py
│       ├── gewicht.py
│       ├── tagesuebersicht.py
│       └── datenexport.py
├── importe/                        einmalige Skripte, nicht Teil der Anwendung
│   ├── import_bls.py               Bundeslebensmittelschlüssel
│   ├── import_sportarten.py        Sportartenkatalog
│   ├── import_met_grundwerte.py    MET-Grundwerte
│   └── import_referenzwerte.py     DGE/ÖGE-Referenzwerte
├── daten/                          Eingangsdaten, im Repository
│   ├── sportarten.csv              25 Sportarten mit Code, MET-Wert, Quelle, Kategorie
│   ├── met_grundwerte.csv          MET-Werte für Schlaf, Arbeit und Restzeit
│   └── DGE-Referenzwerte.xlsx      Referenzwerte und Fußnoten
├── quellen/                        BLS-Quelldateien, nicht im Repository
├── .claude/launch.json             Startkonfiguration für die Vorschau
├── CLAUDE.md                       verbindliche Projektregeln und Datenmodell
├── README.md
├── requirements.txt
└── tracker.db                      wird beim Import angelegt, nicht im Repository
```

### Die sieben Seiten

| Seite | Inhalt |
|---|---|
| **Profilverwaltung** | Profil anlegen (erwachsen oder Kind), Ziel als Modus abnehmen / zunehmen / halten mit Tempo ohne Vorzeichen, Laktoseintoleranz; Wechsel zwischen Profilen |
| **Mahlzeiten** | Datum und Tagesabschnitt wählen, Lebensmittel über Textsuche finden, Menge in Gramm erfassen; Werte je Position und Summe mit der Abdeckung als Mengenanteil, dazu die Prüfung auf hinterlegte Unverträglichkeiten |
| **Lebensmittel** | Eigene Produkte mit Bezeichnung, Hersteller und Nährwertdeklaration erfassen, ändern und archivieren |
| **Aktivität** | Schlaf, Tagestyp mit vorbelegten Arbeitszeiten, Sporteinheiten; Tagesbedarf mit Grundumsatz, Aktivitäts- und Sportanteil sowie vollständiger Aufschlüsselung des Tages |
| **Gewicht** | Gewicht je Datum erfassen, Verlauf über vier Wochen, zwölf Monate oder gesamt, mit gleitendem Durchschnitt über ein Kalenderfenster von sieben Tagen |
| **Tagesübersicht** | Bedarf, Kalorienziel, Aufnahme und Differenz an einem Tag, die Mahlzeiten mit ihren Summen, die Makronährstoffe und der Vergleich mit den DGE-Referenzwerten samt Wochenauswertung |
| **Datenexport** | Wählbaren Zeitraum als ZIP herunterladen: je eine CSV-Datei für Mahlzeitenpositionen, Aktivität und Sport, Gewicht und Tagesbedarf, dazu die Rahmenangaben mit Profil, Zeitraum, Exportdatum und Quellen |

## Datenexport

Ausgegeben wird ein wählbarer Zeitraum des aktiven Profils als ZIP mit CSV-Dateien,
**UTF-8 mit BOM**, Komma als Feldtrennzeichen, Punkt als Dezimaltrennzeichen, Datum als
`JJJJ-MM-TT`. Es ist eine reine Datenausgabe: keine Einstufungen, keine Empfehlungen.

| Datei | Inhalt |
|---|---|
| `rahmenangaben.csv` | Profil, Zeitraum, Exportdatum, Aufbau der Dateien und die verwendeten Quellen mit Version |
| `mahlzeitenpositionen.csv` | eine Zeile je Position, je Nährstoff eine Wert- und eine Herkunftsspalte, auf die erfasste Menge umgerechnet |
| `aktivitaet_und_sport.csv` | eine Zeile je Zeitblock: Schlaf, Arbeit nach Haltung, Sporteinheiten und die berechnete Restzeit, mit MET-Wert und Quelle |
| `gewicht.csv` | nur Tage mit Eintrag |
| `tagesbedarf.csv` | je Tag Grundumsatz, Aktivitäts- und Sportanteil, Bedarf, Kalorienziel, Aufnahme und Differenz |

**Ein leeres Feld bedeutet: kein Wert vorhanden.** Es ist nie als 0 zu lesen. Fehlt die
Zeile in `naehrwert`, bleiben Wert und Herkunft leer; ein Tag ohne Aktivitätseintrag hat
keinen Tagesbedarf, die Felder bleiben leer und der Grund steht in der Spalte `status`.
Eine echte 0 aus der Quelle steht dagegen als 0 in der Datei.

Kinderprofile bekommen dieselben Daten ohne Kalorienbilanz und ohne Zielwerte:
`tagesbedarf.csv` wird nicht erzeugt und die Aktivität ohne Energiespalte ausgegeben.

Excel öffnet die Dateien über **Daten → Aus Text/CSV** mit dem Punkt als
Dezimaltrennzeichen; beim Doppelklick nimmt es die Einstellung des Systems.

## Datenquellen und Lizenz

**Bundeslebensmittelschlüssel 4.0 (2025)** — herausgegeben vom Max Rubner-Institut,
Bundesforschungsinstitut für Ernährung und Lebensmittel. Der BLS ist kostenfrei und
lizenzfrei nutzbar. Bezug über die offizielle Seite des Instituts (blsdb.de). Übernommen
werden 35 Nährstoffe je Lebensmittel: Energie, Protein, Fett, gesättigte Fettsäuren,
Kohlenhydrate, Zucker, Lactose und Salz, dazu 13 Vitamine, sechs Mengenelemente (Natrium,
Chlorid, Kalium, Calcium, Magnesium, Phosphor) und acht Spurenelemente (Eisen, Zink,
Iodid, Kupfer, Mangan, Fluorid, Chrom, Molybdän).

Bei Vitaminen wird nur der Summenparameter übernommen, nicht zusätzlich seine
Einzelkomponenten — sonst entstünde beim Addieren eine Doppelzählung. Die Abdeckung ist
je Nährstoff unterschiedlich: Energie liegt bei 100 Prozent, Vitamin A bei 99,9, Molybdän
bei 81,1. Fehlende Werte erzeugen keine Zeile und damit keine 0.

**DGE/ÖGE-Referenzwerte für die Nährstoffzufuhr**, 3. Auflage, 1. Ausgabe 2025 —
herausgegeben von der Deutschen Gesellschaft für Ernährung und der Österreichischen
Gesellschaft für Ernährung. Übernommen werden 186 Werte für 31 Nährstoffe in drei
Altersgruppen (4 bis unter 7, 7 bis unter 10, 25 bis unter 51 Jahre) je Geschlecht, mit
Kategorie, Bemerkung und Fußnoten. Passt ein Profil in keine dieser Gruppen, gibt es
keinen Referenzwert; es wird nicht auf die nächstliegende Gruppe ausgewichen.

**Compendium of Physical Activities, 2024 Adult Compendium** — Herrmann SD, Willis EA,
Ainsworth BE et al., *Journal of Sport and Health Science*, 2024, https://pacompendium.com.
Die Nutzung verlangt eine **Quellenangabe**, und die **MET-Werte dürfen nicht verändert
werden**. Sie stehen deshalb ausschließlich in `daten/sportarten.csv` und
`daten/met_grundwerte.csv` und werden unverändert übernommen; im Programmcode steht kein
einziger MET-Wert.

## Grundregeln der Anwendung

Ausführlich in [CLAUDE.md](CLAUDE.md), in Kurzform:

1. **Unbekannt ist nicht null.** Fehlt ein Wert in der Quelle (Strich, „TR", Angabe unter
   der Nachweisgrenze), entsteht keine Zeile und keine 0. Er wird als *unbekannt*
   ausgewiesen und geht nicht in Summen ein. Eine echte 0 aus der Quelle wird gespeichert.
2. **Abdeckung ausweisen, als Mengenanteil.** Jede Summe nennt, welcher Anteil der
   erfassten Menge einen Wert hat, etwa „82 % der erfassten Menge, 410 g von 500 g" — nicht
   die Zahl der Lebensmittel. 200 g ohne Nährwert wiegen schwerer als 5 g.
3. **Verweis statt Zahl.** Gespeichert werden Lebensmittel und Menge, nie ein berechneter
   Nährwert. Die Werte werden bei jeder Anzeige frisch nachgeschlagen.
4. **Berechnet, nachgeschlagen oder von der KI** bleiben in der Anzeige getrennt.
5. **Keine Ersatzannahmen.** Ohne Aktivitätseintrag gibt es keinen Tagesbedarf, ohne
   erfasste Mahlzeit keine Bilanz — nicht ersatzweise gegen den Grundumsatz oder eine
   Aufnahme von 0 kcal gerechnet.
6. **Der Profiltyp steuert.** Was ein Kinderprofil nicht bekommt, wird nicht ausgegraut,
   sondern gar nicht erst aufgebaut. Kinderprofile haben kein Ziel, keine Arbeitszeit und
   keinen Tagesbedarf.
7. **Eine Einheit je Nährstoff**, sie steht ausschließlich in der Tabelle `naehrstoff`.
8. **Keine medizinischen Aussagen.** Kein „Mangel", keine Ursachen für Beschwerden, keine
   Ernährungsempfehlung — die Anwendung rechnet und weist aus.

## Stand

Umgesetzt:

- Profile für Erwachsene und Kinder, Zielmodus mit Umstellung auf *halten* beim Erreichen
  des Zielgewichts, Laktoseintoleranz mit Verweis auf den Lactose-Nährstoff
- Mahlzeiten mit Textsuche im BLS, Positionen einzeln löschbar, Nährwerte je Position und
  je Mahlzeit
- Tagesstruktur mit Schlaf, Tagestypen, Sport in zwei Stufen (Kategorie, Intensität) und
  vollständiger Tagesbedarfsrechnung samt Kalorienziel
- Gewichtsverlauf mit gleitendem Durchschnitt über ein Kalenderfenster
- Tagesübersicht als Zusammenführung von Bedarf und Aufnahme
- Vergleich der Zufuhr mit den DGE-Referenzwerten, gruppiert nach energieliefernden
  Nährstoffen, Vitaminen und Mineralstoffen, dazu eine Auswertung über sieben Tage
- Prüfung auf hinterlegte Unverträglichkeiten je Mahlzeitenposition
- Eigene Lebensmittel mit Nährwertdeklaration anlegen, ändern und archivieren
- Datenexport eines Zeitraums als ZIP mit fünf CSV-Dateien, UTF-8 mit BOM

Offen:

- KI-Hinweise (`ki_hinweis`) sind im Datenmodell beschrieben, die Tabelle wird noch nicht
  angelegt
- Fructose und Zuckeralkohole werden noch nicht importiert; die Unverträglichkeitsprüfung
  könnte sie ohne Codeänderung mitnehmen
- Nährstoffe mit Bezug auf den Energieanteil (Fett, Kohlenhydrate) werden noch nicht mit
  ihren Referenzwerten verglichen

Bewusst nicht vorgesehen sind Sätze und Wiederholungen im Training, Bilderkennung von
Mahlzeiten, Wearable-Anbindung, Cloud-Speicherung und Rezepte.

## Autor

Uygar Ucar
