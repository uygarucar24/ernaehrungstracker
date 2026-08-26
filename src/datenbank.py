"""Zugriff auf tracker.db.

Legt die Tabellen an, die die Anwendung selbst füllt (profil, gewicht,
unvertraeglichkeit). lebensmittel, naehrstoff und naehrwert stammen aus
import_bls.py und werden hier nur gelesen.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Iterator

BASIS = Path(__file__).resolve().parent.parent
DATENBANK = BASIS / "tracker.db"

# Der Modus bestimmt die Richtung. Eingegeben wird nur das Tempo ohne Vorzeichen,
# das Vorzeichen von aenderung_kg_woche setzt die Anwendung daraus.
ZIEL_MODI = ("abnehmen", "zunehmen", "halten")

SCHEMA = """
CREATE TABLE IF NOT EXISTS profil (
    profil_id          INTEGER PRIMARY KEY,
    name               TEXT NOT NULL,
    geburtsdatum       DATE NOT NULL,
    geschlecht         TEXT NOT NULL,
    groesse_cm         REAL NOT NULL,
    typ                TEXT NOT NULL,
    ziel_modus         TEXT,
    zielgewicht_kg     REAL,
    aenderung_kg_woche REAL
);

CREATE TABLE IF NOT EXISTS gewicht (
    profil_id  INTEGER NOT NULL REFERENCES profil(profil_id),
    datum      DATE NOT NULL,
    gewicht_kg REAL NOT NULL,
    notiz      TEXT,
    PRIMARY KEY (profil_id, datum)
);

CREATE TABLE IF NOT EXISTS unvertraeglichkeit (
    unvertraeglichkeit_id INTEGER PRIMARY KEY,
    profil_id             INTEGER NOT NULL REFERENCES profil(profil_id),
    art                   TEXT NOT NULL,
    bezeichnung           TEXT NOT NULL,
    pruefweg              TEXT NOT NULL,
    naehrstoff_id         INTEGER REFERENCES naehrstoff(naehrstoff_id),
    schwelle_je_100g      REAL,
    aktiv                 INTEGER NOT NULL DEFAULT 1
);
"""


class DatenFehler(RuntimeError):
    """Wird geworfen, wenn ein Schreibvorgang nicht sauber möglich ist."""


@contextmanager
def verbindung() -> Iterator[sqlite3.Connection]:
    """Verbindung je Vorgang: schließt am Ende und schreibt die Änderungen fest."""
    con = sqlite3.connect(DATENBANK)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        with con:
            yield con
    finally:
        con.close()


def schema_anlegen() -> None:
    """Legt die Tabellen der Anwendung an, falls sie noch nicht existieren."""
    with verbindung() as con:
        con.executescript(SCHEMA)
        _ziel_modus_nachruesten(con)


def _ziel_modus_nachruesten(con: sqlite3.Connection) -> None:
    """Ergänzt ziel_modus in älteren Datenbanken und leitet den Wert einmalig ab.

    Die Richtung kommt aus dem Verhältnis von Zielgewicht zum letzten bekannten
    Gewicht, das bisherige Vorzeichen der Rate wird verworfen. Ohne Zielgewicht
    oder ohne Rate lässt sich keine Richtung begründen, dann gilt halten.
    """
    spalten = [zeile["name"] for zeile in con.execute("PRAGMA table_info(profil)")]
    if "ziel_modus" in spalten:
        return

    con.execute("ALTER TABLE profil ADD COLUMN ziel_modus TEXT")

    for zeile in con.execute(
        "SELECT profil_id, typ, zielgewicht_kg, aenderung_kg_woche FROM profil"
    ).fetchall():
        if zeile["typ"] != "erwachsen":
            con.execute(
                "UPDATE profil SET ziel_modus = NULL, zielgewicht_kg = NULL, "
                "aenderung_kg_woche = NULL WHERE profil_id = ?",
                (zeile["profil_id"],),
            )
            continue

        aktuell = con.execute(
            "SELECT gewicht_kg FROM gewicht WHERE profil_id = ? ORDER BY datum DESC LIMIT 1",
            (zeile["profil_id"],),
        ).fetchone()

        ziel = zeile["zielgewicht_kg"]
        tempo = abs(zeile["aenderung_kg_woche"] or 0.0)
        modus = "halten"
        if ziel is not None and aktuell is not None and tempo > 0:
            if ziel < aktuell["gewicht_kg"]:
                modus = "abnehmen"
            elif ziel > aktuell["gewicht_kg"]:
                modus = "zunehmen"

        if modus == "halten":
            con.execute(
                "UPDATE profil SET ziel_modus = 'halten', zielgewicht_kg = NULL, "
                "aenderung_kg_woche = NULL WHERE profil_id = ?",
                (zeile["profil_id"],),
            )
        else:
            con.execute(
                "UPDATE profil SET ziel_modus = ?, aenderung_kg_woche = ? WHERE profil_id = ?",
                (modus, -tempo if modus == "abnehmen" else tempo, zeile["profil_id"]),
            )


# --------------------------------------------------------------------------- #
# Lesen
# --------------------------------------------------------------------------- #
def profile() -> list[sqlite3.Row]:
    with verbindung() as con:
        return con.execute(
            "SELECT profil_id, name, typ FROM profil ORDER BY name"
        ).fetchall()


def profil(profil_id: int) -> sqlite3.Row | None:
    with verbindung() as con:
        return con.execute(
            "SELECT * FROM profil WHERE profil_id = ?", (profil_id,)
        ).fetchone()


def letztes_gewicht(profil_id: int) -> sqlite3.Row | None:
    """Jüngster Eintrag aus gewicht. None, wenn noch nichts erfasst wurde."""
    with verbindung() as con:
        return con.execute(
            "SELECT datum, gewicht_kg FROM gewicht WHERE profil_id = ? "
            "ORDER BY datum DESC LIMIT 1",
            (profil_id,),
        ).fetchone()


def unvertraeglichkeiten(profil_id: int, nur_aktive: bool = True) -> list[sqlite3.Row]:
    bedingung = " AND aktiv = 1" if nur_aktive else ""
    with verbindung() as con:
        return con.execute(
            "SELECT * FROM unvertraeglichkeit WHERE profil_id = ?" + bedingung,
            (profil_id,),
        ).fetchall()


def naehrstoff_id(bls_spalte: str) -> int | None:
    """Sucht einen Nährstoff über seinen BLS-Code, z. B. LACS."""
    with verbindung() as con:
        try:
            zeile = con.execute(
                "SELECT naehrstoff_id FROM naehrstoff WHERE bls_spalte = ?",
                (bls_spalte,),
            ).fetchone()
        except sqlite3.OperationalError:
            return None  # naehrstoff gibt es noch nicht, import_bls.py fehlt
    return zeile["naehrstoff_id"] if zeile else None


# --------------------------------------------------------------------------- #
# Schreiben
# --------------------------------------------------------------------------- #
def _ziel_pruefen(
    ziel_modus: str | None,
    zielgewicht_kg: float | None,
    tempo_kg_woche: float | None,
    gewicht_kg: float,
) -> tuple[str, float | None, float | None]:
    """Prüft das Ziel und setzt das Vorzeichen der Rate aus dem Modus.

    Gibt (ziel_modus, zielgewicht_kg, aenderung_kg_woche) zurück. Bei halten
    bleiben Zielgewicht und Rate leer.
    """
    if ziel_modus not in ZIEL_MODI:
        raise DatenFehler(f"Unbekannter Zielmodus: {ziel_modus!r}")

    if ziel_modus == "halten":
        return "halten", None, None

    if zielgewicht_kg is None or tempo_kg_woche is None:
        raise DatenFehler("Für Abnehmen und Zunehmen werden Zielgewicht und Tempo gebraucht.")

    tempo = abs(float(tempo_kg_woche))
    if tempo == 0:
        raise DatenFehler("Das Tempo muss größer als 0 sein. Sonst passt der Modus halten.")

    if ziel_modus == "abnehmen":
        if zielgewicht_kg >= gewicht_kg:
            raise DatenFehler(
                "Beim Abnehmen muss das Zielgewicht unter dem aktuellen Gewicht liegen."
            )
        return "abnehmen", float(zielgewicht_kg), -tempo

    if zielgewicht_kg <= gewicht_kg:
        raise DatenFehler(
            "Beim Zunehmen muss das Zielgewicht über dem aktuellen Gewicht liegen."
        )
    return "zunehmen", float(zielgewicht_kg), tempo


def ziel_status_aktualisieren(profil_id: int) -> bool:
    """Stellt auf halten um, sobald das Zielgewicht erreicht ist.

    Gibt True zurück, wenn dabei umgestellt wurde. Grundlage ist der jüngste
    Eintrag in gewicht; ohne Gewichtseintrag bleibt alles unverändert.
    """
    with verbindung() as con:
        eintrag = con.execute(
            "SELECT typ, ziel_modus, zielgewicht_kg FROM profil WHERE profil_id = ?",
            (profil_id,),
        ).fetchone()
        if (
            eintrag is None
            or eintrag["typ"] != "erwachsen"
            or eintrag["ziel_modus"] not in ("abnehmen", "zunehmen")
            or eintrag["zielgewicht_kg"] is None
        ):
            return False

        gewicht = con.execute(
            "SELECT gewicht_kg FROM gewicht WHERE profil_id = ? ORDER BY datum DESC LIMIT 1",
            (profil_id,),
        ).fetchone()
        if gewicht is None:
            return False

        if eintrag["ziel_modus"] == "abnehmen":
            erreicht = gewicht["gewicht_kg"] <= eintrag["zielgewicht_kg"]
        else:
            erreicht = gewicht["gewicht_kg"] >= eintrag["zielgewicht_kg"]
        if not erreicht:
            return False

        con.execute(
            "UPDATE profil SET ziel_modus = 'halten', zielgewicht_kg = NULL, "
            "aenderung_kg_woche = NULL WHERE profil_id = ?",
            (profil_id,),
        )
    return True


def profil_anlegen(
    name: str,
    geburtsdatum: date,
    geschlecht: str,
    groesse_cm: float,
    typ: str,
    gewicht_kg: float,
    ziel_modus: str | None,
    zielgewicht_kg: float | None,
    tempo_kg_woche: float | None,
    laktoseintoleranz: bool,
) -> int:
    """Legt Profil, ersten Gewichtseintrag und Unverträglichkeiten gemeinsam an.

    Das eingegebene Gewicht steht nicht im Profil, sondern als erste Zeile in
    gewicht mit dem heutigen Datum. tempo_kg_woche wird ohne Vorzeichen
    übergeben, das Vorzeichen ergibt sich aus ziel_modus.
    """
    # Der Profiltyp steuert, nicht das leere Feld: Kinderprofile bekommen hier
    # ausdrücklich weder Modus noch Ziel noch Rate, egal was übergeben wurde.
    if typ == "kind":
        ziel_modus = None
        zielgewicht_kg = None
        aenderung_kg_woche = None
    else:
        ziel_modus, zielgewicht_kg, aenderung_kg_woche = _ziel_pruefen(
            ziel_modus, zielgewicht_kg, tempo_kg_woche, gewicht_kg
        )

    lactose_id = naehrstoff_id("LACS") if laktoseintoleranz else None
    if laktoseintoleranz and lactose_id is None:
        raise DatenFehler(
            "Der Nährstoff Lactose (LACS) fehlt in der Datenbank. "
            "Bitte zuerst import_bls.py ausführen."
        )

    with verbindung() as con:
        cursor = con.execute(
            "INSERT INTO profil (name, geburtsdatum, geschlecht, groesse_cm, typ, "
            "ziel_modus, zielgewicht_kg, aenderung_kg_woche) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                name,
                geburtsdatum.isoformat(),
                geschlecht,
                groesse_cm,
                typ,
                ziel_modus,
                zielgewicht_kg,
                aenderung_kg_woche,
            ),
        )
        neue_id = cursor.lastrowid

        con.execute(
            "INSERT INTO gewicht (profil_id, datum, gewicht_kg, notiz) VALUES (?, ?, ?, NULL)",
            (neue_id, date.today().isoformat(), gewicht_kg),
        )

        if laktoseintoleranz:
            con.execute(
                "INSERT INTO unvertraeglichkeit (profil_id, art, bezeichnung, pruefweg, "
                "naehrstoff_id, schwelle_je_100g, aktiv) "
                "VALUES (?, 'unvertraeglichkeit', 'laktose', 'bls', ?, NULL, 1)",
                (neue_id, lactose_id),
            )

    return neue_id
