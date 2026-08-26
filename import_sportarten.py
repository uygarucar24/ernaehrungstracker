"""Import des Sportartenkatalogs in tracker.db.

Nicht Teil der Anwendung. Liest daten/sportarten.csv mit den Spalten
code, name, met, quelle und füllt die Tabelle sportart.

Der Code wird als Text gespeichert, damit führende Nullen erhalten bleiben.
Die MET-Werte werden unverändert aus der Datei übernommen. Ein zweiter Lauf
erzeugt keine Duplikate: vorhandene Codes werden aktualisiert.

Aufruf:
    python import_sportarten.py
"""

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

BASIS = Path(__file__).resolve().parent
QUELLE = BASIS / "daten" / "sportarten.csv"
DATENBANK = BASIS / "tracker.db"

ERWARTETE_SPALTEN = ("code", "name", "met", "quelle")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sportart (
    sportart_id INTEGER PRIMARY KEY,
    code        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    met_wert    REAL NOT NULL,
    quelle      TEXT
);
"""


def pruefe_kopfzeile(spalten):
    """Bricht ab, wenn die Datei nicht die erwarteten Spalten hat."""
    vorhanden = [(spalte or "").strip().lower() for spalte in spalten or []]
    fehlend = [name for name in ERWARTETE_SPALTEN if name not in vorhanden]
    if fehlend:
        print("Abbruch. Die Kopfzeile passt nicht:", file=sys.stderr)
        print(f"  gefunden:  {vorhanden}", file=sys.stderr)
        print(f"  erwartet:  {list(ERWARTETE_SPALTEN)}", file=sys.stderr)
        print(f"  fehlt:     {fehlend}", file=sys.stderr)
        sys.exit(1)


def trennzeichen(kopfzeile: str) -> str:
    """Komma oder Semikolon, je nachdem was in der Kopfzeile steht."""
    return ";" if kopfzeile.count(";") > kopfzeile.count(",") else ","


def lies_met(rohwert):
    """Gibt den MET-Wert als Zahl zurück oder None, wenn er nicht lesbar ist."""
    text = (rohwert or "").strip().replace(",", ".")
    if not text:
        return None
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
            code = (zeile.get("code") or "").strip()
            name = (zeile.get("name") or "").strip()
            met = lies_met(zeile.get("met"))
            quellencode = (zeile.get("quelle") or "").strip() or None

            if not code or not name or met is None:
                uebersprungen.append(
                    f"Zeile {zeilennummer}: code={code!r} name={name!r} met={zeile.get('met')!r}"
                )
                continue

            vorhanden = verbindung.execute(
                "SELECT sportart_id FROM sportart WHERE code = ?", (code,)
            ).fetchone()
            if vorhanden:
                verbindung.execute(
                    "UPDATE sportart SET name = ?, met_wert = ?, quelle = ? WHERE code = ?",
                    (name, met, quellencode, code),
                )
                aktualisiert += 1
            else:
                verbindung.execute(
                    "INSERT INTO sportart (code, name, met_wert, quelle) VALUES (?, ?, ?, ?)",
                    (code, name, met, quellencode),
                )
                neu += 1

    verbindung.commit()
    gesamt = verbindung.execute("SELECT COUNT(*) FROM sportart").fetchone()[0]
    beispiele = verbindung.execute(
        "SELECT code, name, met_wert, quelle FROM sportart ORDER BY code LIMIT 3"
    ).fetchall()
    verbindung.close()

    print()
    print("Import abgeschlossen")
    print(f"  Zeilen gelesen:        {gelesen}")
    print(f"  neu angelegt:          {neu}")
    print(f"  aktualisiert:          {aktualisiert}")
    print(f"  uebersprungen:         {len(uebersprungen)}")
    for hinweis in uebersprungen:
        print(f"    - {hinweis}")
    print(f"  Sportarten insgesamt:  {gesamt}")

    print()
    print("  Erste Eintraege (Code als Text, fuehrende Nullen bleiben):")
    for zeile in beispiele:
        print(f"    {zeile['code']!r:<10} {zeile['name']:<38} MET {zeile['met_wert']:<6} {zeile['quelle']}")


def main():
    parser = argparse.ArgumentParser(description="Sportartenkatalog nach tracker.db importieren")
    parser.add_argument("--quelle", type=Path, default=QUELLE, help="Pfad zur CSV-Datei")
    parser.add_argument("--db", type=Path, default=DATENBANK, help="Pfad zur SQLite-Datenbank")
    argumente = parser.parse_args()
    importiere(argumente.quelle, argumente.db)


if __name__ == "__main__":
    main()
