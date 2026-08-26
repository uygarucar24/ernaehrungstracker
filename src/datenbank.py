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

SCHEMA = """
CREATE TABLE IF NOT EXISTS profil (
    profil_id          INTEGER PRIMARY KEY,
    name               TEXT NOT NULL,
    geburtsdatum       DATE NOT NULL,
    geschlecht         TEXT NOT NULL,
    groesse_cm         REAL NOT NULL,
    typ                TEXT NOT NULL,
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
def profil_anlegen(
    name: str,
    geburtsdatum: date,
    geschlecht: str,
    groesse_cm: float,
    typ: str,
    gewicht_kg: float,
    zielgewicht_kg: float | None,
    aenderung_kg_woche: float | None,
    laktoseintoleranz: bool,
) -> int:
    """Legt Profil, ersten Gewichtseintrag und Unverträglichkeiten gemeinsam an.

    Das eingegebene Gewicht steht nicht im Profil, sondern als erste Zeile in
    gewicht mit dem heutigen Datum.
    """
    # Der Profiltyp steuert, nicht das leere Feld: Kinderprofile bekommen hier
    # ausdrücklich kein Ziel und keine Änderungsrate, egal was übergeben wurde.
    if typ == "kind":
        zielgewicht_kg = None
        aenderung_kg_woche = None

    lactose_id = naehrstoff_id("LACS") if laktoseintoleranz else None
    if laktoseintoleranz and lactose_id is None:
        raise DatenFehler(
            "Der Nährstoff Lactose (LACS) fehlt in der Datenbank. "
            "Bitte zuerst import_bls.py ausführen."
        )

    with verbindung() as con:
        cursor = con.execute(
            "INSERT INTO profil (name, geburtsdatum, geschlecht, groesse_cm, typ, "
            "zielgewicht_kg, aenderung_kg_woche) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                name,
                geburtsdatum.isoformat(),
                geschlecht,
                groesse_cm,
                typ,
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
