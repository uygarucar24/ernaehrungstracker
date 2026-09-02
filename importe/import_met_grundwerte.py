"""Import der MET-Grundwerte in tracker.db.

Nicht Teil der Anwendung. Liest daten/met_grundwerte.csv mit den Spalten
schluessel, name, met, code, quelle und füllt die Tabelle met_grundwert.

Diese Tabelle ist die einzige Quelle für die MET-Werte von Schlaf, sitzender
und stehender Arbeit, Veranstaltung und Restzeit. Im Code stehen keine
MET-Werte mehr. Ein zweiter Lauf erzeugt keine Duplikate.

Aufruf aus dem Projektordner:
    python importe/import_met_grundwerte.py
"""

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

# Das Skript liegt in importe/, die Datenbank und die Datenordner eine Ebene darueber.
BASIS = Path(__file__).resolve().parent.parent
QUELLE = BASIS / "daten" / "met_grundwerte.csv"
DATENBANK = BASIS / "tracker.db"

ERWARTETE_SPALTEN = ("schluessel", "name", "met", "code", "quelle")

# Diese Schlüssel braucht die Anwendung, um einen Tag vollständig aufzuteilen.
BENOETIGTE_SCHLUESSEL = ("schlaf", "sitzend", "stehend", "veranstaltung", "alltag")

SCHEMA = """
CREATE TABLE IF NOT EXISTS met_grundwert (
    schluessel TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    met        REAL NOT NULL,
    code       TEXT,
    quelle     TEXT
);
"""


def pruefe_kopfzeile(spalten):
    vorhanden = [(spalte or "").strip().lower() for spalte in spalten or []]
    fehlend = [name for name in ERWARTETE_SPALTEN if name not in vorhanden]
    if fehlend:
        print("Abbruch. Die Kopfzeile passt nicht:", file=sys.stderr)
        print(f"  gefunden: {vorhanden}", file=sys.stderr)
        print(f"  erwartet: {list(ERWARTETE_SPALTEN)}", file=sys.stderr)
        sys.exit(1)


def trennzeichen(kopfzeile: str) -> str:
    return ";" if kopfzeile.count(";") > kopfzeile.count(",") else ","


def lies_met(rohwert):
    text = (rohwert or "").strip().replace(",", ".")
    try:
        wert = float(text)
    except ValueError:
        return None
    return wert if wert > 0 else None


def importiere(quelle: Path, datenbank: Path) -> None:
    if not quelle.exists():
        sys.exit(f"Quelldatei nicht gefunden: {quelle}")

    print(f"Quelle:    {quelle}")
    print(f"Datenbank: {datenbank}")

    verbindung = sqlite3.connect(datenbank)
    verbindung.row_factory = sqlite3.Row
    verbindung.executescript(SCHEMA)

    gelesen = neu = aktualisiert = 0
    uebersprungen = []

    with quelle.open(encoding="utf-8-sig", newline="") as datei:
        erste_zeile = datei.readline()
        datei.seek(0)
        leser = csv.DictReader(datei, delimiter=trennzeichen(erste_zeile))
        pruefe_kopfzeile(leser.fieldnames)

        for zeilennummer, zeile in enumerate(leser, start=2):
            gelesen += 1
            schluessel = (zeile.get("schluessel") or "").strip().lower()
            name = (zeile.get("name") or "").strip()
            met = lies_met(zeile.get("met"))
            code = (zeile.get("code") or "").strip() or None
            quellencode = (zeile.get("quelle") or "").strip() or None

            if not schluessel or not name or met is None:
                uebersprungen.append(
                    f"Zeile {zeilennummer}: schluessel={schluessel!r} met={zeile.get('met')!r}"
                )
                continue

            vorhanden = verbindung.execute(
                "SELECT 1 FROM met_grundwert WHERE schluessel = ?", (schluessel,)
            ).fetchone()
            if vorhanden:
                verbindung.execute(
                    "UPDATE met_grundwert SET name = ?, met = ?, code = ?, quelle = ? "
                    "WHERE schluessel = ?",
                    (name, met, code, quellencode, schluessel),
                )
                aktualisiert += 1
            else:
                verbindung.execute(
                    "INSERT INTO met_grundwert (schluessel, name, met, code, quelle) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (schluessel, name, met, code, quellencode),
                )
                neu += 1

    verbindung.commit()

    gespeichert = verbindung.execute(
        "SELECT schluessel, name, met, code, quelle FROM met_grundwert ORDER BY schluessel"
    ).fetchall()
    verbindung.close()

    print()
    print("Import abgeschlossen")
    print(f"  Zeilen gelesen: {gelesen}")
    print(f"  neu angelegt:   {neu}")
    print(f"  aktualisiert:   {aktualisiert}")
    print(f"  uebersprungen:  {len(uebersprungen)}")
    for hinweis in uebersprungen:
        print(f"    - {hinweis}")

    print()
    print("  Tabelle met_grundwert:")
    for zeile in gespeichert:
        print(
            f"    {zeile['schluessel']:<14} {zeile['name']:<26} MET {zeile['met']:<5} "
            f"{zeile['code']} / {zeile['quelle']}"
        )

    fehlend = [
        schluessel
        for schluessel in BENOETIGTE_SCHLUESSEL
        if schluessel not in {zeile["schluessel"] for zeile in gespeichert}
    ]
    if fehlend:
        print()
        print(f"  ACHTUNG: Die Anwendung braucht zusaetzlich: {fehlend}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="MET-Grundwerte nach tracker.db importieren")
    parser.add_argument("--quelle", type=Path, default=QUELLE, help="Pfad zur CSV-Datei")
    parser.add_argument("--db", type=Path, default=DATENBANK, help="Pfad zur SQLite-Datenbank")
    argumente = parser.parse_args()
    importiere(argumente.quelle, argumente.db)


if __name__ == "__main__":
    main()
