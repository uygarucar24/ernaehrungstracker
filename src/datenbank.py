"""Zugriff auf tracker.db.

Legt die Tabellen an, die die Anwendung selbst füllt (profil, gewicht,
unvertraeglichkeit). lebensmittel, naehrstoff und naehrwert stammen aus
import_bls.py und werden hier nur gelesen.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

from . import berechnung

BASIS = Path(__file__).resolve().parent.parent
DATENBANK = BASIS / "tracker.db"

# Der Modus bestimmt die Richtung. Eingegeben wird nur das Tempo ohne Vorzeichen,
# das Vorzeichen von aenderung_kg_woche setzt die Anwendung daraus.
ZIEL_MODI = ("abnehmen", "zunehmen", "halten")

# Feste Werteliste, kein Freitext.
TAGESABSCHNITTE = ("fruehstueck", "mittag", "abend", "snack")

# Bezugsmenge der Nährwerte: naehrwert.wert_je_100g gilt je 100 Gramm.
BEZUGSMENGE_G = 100.0

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

CREATE TABLE IF NOT EXISTS tag_aktivitaet (
    profil_id         INTEGER NOT NULL REFERENCES profil(profil_id),
    datum             DATE NOT NULL,
    min_schlaf        INTEGER NOT NULL DEFAULT 0,
    min_sitzend       INTEGER NOT NULL,
    min_stehend       INTEGER NOT NULL,
    min_veranstaltung INTEGER NOT NULL,
    tagestyp          TEXT,
    PRIMARY KEY (profil_id, datum)
);

CREATE TABLE IF NOT EXISTS met_grundwert (
    schluessel TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    met        REAL NOT NULL,
    code       TEXT,
    quelle     TEXT
);

CREATE TABLE IF NOT EXISTS sportart (
    sportart_id INTEGER PRIMARY KEY,
    code        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    met_wert    REAL NOT NULL,
    quelle      TEXT
);

CREATE TABLE IF NOT EXISTS sporteinheit (
    einheit_id  INTEGER PRIMARY KEY,
    profil_id   INTEGER NOT NULL REFERENCES profil(profil_id),
    datum       DATE NOT NULL,
    sportart_id INTEGER NOT NULL REFERENCES sportart(sportart_id),
    dauer_min   INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sporteinheit_tag ON sporteinheit(profil_id, datum);

CREATE TABLE IF NOT EXISTS tagesbedarf (
    profil_id            INTEGER NOT NULL REFERENCES profil(profil_id),
    datum                DATE NOT NULL,
    gewicht_kg_verwendet REAL NOT NULL,
    grundumsatz_kcal     REAL NOT NULL,
    aktivitaet_kcal      REAL NOT NULL,
    sport_kcal           REAL NOT NULL,
    bedarf_kcal          REAL NOT NULL,
    berechnet_am         DATETIME NOT NULL,
    PRIMARY KEY (profil_id, datum)
);

CREATE TABLE IF NOT EXISTS mahlzeit (
    mahlzeit_id    INTEGER PRIMARY KEY,
    profil_id      INTEGER NOT NULL REFERENCES profil(profil_id),
    datum          DATE NOT NULL,
    tagesabschnitt TEXT NOT NULL,
    UNIQUE (profil_id, datum, tagesabschnitt)
);

CREATE TABLE IF NOT EXISTS mahlzeit_position (
    position_id      INTEGER PRIMARY KEY,
    mahlzeit_id      INTEGER NOT NULL REFERENCES mahlzeit(mahlzeit_id),
    lebensmittel_id  INTEGER NOT NULL REFERENCES lebensmittel(lebensmittel_id),
    menge_g          REAL NOT NULL,
    uhrzeit          TIME,
    eingabe_original TEXT,
    zuordnung_weg    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_position_mahlzeit ON mahlzeit_position(mahlzeit_id);

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
        # Ältere Datenbanken kennen diese Spalten noch nicht.
        _spalte_ergaenzen(con, "tag_aktivitaet", "min_schlaf", "INTEGER NOT NULL DEFAULT 0")
        _spalte_ergaenzen(con, "tag_aktivitaet", "tagestyp", "TEXT")
        _spalte_ergaenzen(con, "sportart", "kategorie", "TEXT")


def _spalte_ergaenzen(con: sqlite3.Connection, tabelle: str, spalte: str, typ: str) -> None:
    vorhanden = [zeile["name"] for zeile in con.execute(f"PRAGMA table_info({tabelle})")]
    if vorhanden and spalte not in vorhanden:
        con.execute(f"ALTER TABLE {tabelle} ADD COLUMN {spalte} {typ}")


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
# Lebensmittel, Nährstoffe, Mahlzeiten
# --------------------------------------------------------------------------- #
def lebensmittel_suchen(text: str, grenze: int = 50) -> list[sqlite3.Row]:
    """Einfache Textsuche in lebensmittel.bezeichnung, ohne KI.

    Alle Suchbegriffe müssen vorkommen, Reihenfolge und Groß-/Kleinschreibung
    spielen keine Rolle. Mitgeliefert werden die Kilokalorien je 100 Gramm,
    damit die Auswahl nachvollziehbar ist; fehlen sie, steht dort None.
    """
    begriffe = [teil for teil in text.lower().split() if teil]
    if not begriffe:
        return []

    bedingungen = " AND ".join(["klein(l.bezeichnung) LIKE ?"] * len(begriffe))
    with verbindung() as con:
        # SQLite kennt kleingeschriebene Umlaute nicht, deshalb Pythons lower().
        con.create_function("klein", 1, lambda wert: (wert or "").lower())
        return con.execute(
            "SELECT l.lebensmittel_id, l.bezeichnung, ("
            "  SELECT w.wert_je_100g FROM naehrwert w JOIN naehrstoff n"
            "  ON n.naehrstoff_id = w.naehrstoff_id"
            "  WHERE w.lebensmittel_id = l.lebensmittel_id AND n.bls_spalte = 'ENERCC'"
            ") AS kcal_je_100g "
            "FROM lebensmittel l "
            f"WHERE l.archiviert = 0 AND {bedingungen} "
            "ORDER BY LENGTH(l.bezeichnung), l.bezeichnung LIMIT ?",
            [f"%{begriff}%" for begriff in begriffe] + [grenze],
        ).fetchall()


def naehrstoffe(codes: tuple[str, ...]) -> dict[str, sqlite3.Row]:
    """Stammdaten je BLS-Code. Die Einheit steht ausschließlich in naehrstoff."""
    platzhalter = ",".join("?" * len(codes))
    with verbindung() as con:
        zeilen = con.execute(
            f"SELECT naehrstoff_id, bls_spalte, name, einheit FROM naehrstoff "
            f"WHERE bls_spalte IN ({platzhalter})",
            codes,
        ).fetchall()
    return {zeile["bls_spalte"]: zeile for zeile in zeilen}


def naehrwerte(lebensmittel_ids: list[int], codes: tuple[str, ...]) -> dict[tuple[int, str], float]:
    """Werte je 100 Gramm für mehrere Lebensmittel auf einmal.

    Fehlt ein Wert, fehlt auch der Schlüssel. Kein Eintrag bedeutet unbekannt,
    niemals 0.
    """
    if not lebensmittel_ids:
        return {}
    lm_platzhalter = ",".join("?" * len(lebensmittel_ids))
    code_platzhalter = ",".join("?" * len(codes))
    with verbindung() as con:
        zeilen = con.execute(
            "SELECT w.lebensmittel_id, n.bls_spalte, w.wert_je_100g "
            "FROM naehrwert w JOIN naehrstoff n ON n.naehrstoff_id = w.naehrstoff_id "
            f"WHERE w.lebensmittel_id IN ({lm_platzhalter}) "
            f"AND n.bls_spalte IN ({code_platzhalter})",
            list(lebensmittel_ids) + list(codes),
        ).fetchall()
    return {(z["lebensmittel_id"], z["bls_spalte"]): z["wert_je_100g"] for z in zeilen}


def mahlzeit_positionen(profil_id: int, datum: date, tagesabschnitt: str) -> list[sqlite3.Row]:
    """Positionen einer Mahlzeit in der Reihenfolge ihrer Erfassung."""
    with verbindung() as con:
        return con.execute(
            "SELECT p.position_id, p.lebensmittel_id, p.menge_g, l.bezeichnung "
            "FROM mahlzeit_position p "
            "JOIN mahlzeit m ON m.mahlzeit_id = p.mahlzeit_id "
            "JOIN lebensmittel l ON l.lebensmittel_id = p.lebensmittel_id "
            "WHERE m.profil_id = ? AND m.datum = ? AND m.tagesabschnitt = ? "
            "ORDER BY p.position_id",
            (profil_id, datum.isoformat(), tagesabschnitt),
        ).fetchall()


def position_hinzufuegen(
    profil_id: int,
    datum: date,
    tagesabschnitt: str,
    lebensmittel_id: int,
    menge_g: float,
    zuordnung_weg: str = "direkt",
) -> int:
    """Hängt eine Position an die Mahlzeit und legt sie an, falls es sie nicht gibt.

    Je Profil, Datum und Tagesabschnitt gibt es genau eine Mahlzeit; die Regel
    steht als UNIQUE in der Datenbank. Gespeichert werden nur Lebensmittel und
    Menge, keine berechneten Nährwerte.
    """
    if tagesabschnitt not in TAGESABSCHNITTE:
        raise DatenFehler(f"Unbekannter Tagesabschnitt: {tagesabschnitt!r}")
    if menge_g <= 0:
        raise DatenFehler("Die Menge muss größer als 0 Gramm sein.")

    with verbindung() as con:
        con.execute(
            "INSERT OR IGNORE INTO mahlzeit (profil_id, datum, tagesabschnitt) VALUES (?, ?, ?)",
            (profil_id, datum.isoformat(), tagesabschnitt),
        )
        mahlzeit_id = con.execute(
            "SELECT mahlzeit_id FROM mahlzeit "
            "WHERE profil_id = ? AND datum = ? AND tagesabschnitt = ?",
            (profil_id, datum.isoformat(), tagesabschnitt),
        ).fetchone()["mahlzeit_id"]

        cursor = con.execute(
            "INSERT INTO mahlzeit_position (mahlzeit_id, lebensmittel_id, menge_g, "
            "uhrzeit, eingabe_original, zuordnung_weg) VALUES (?, ?, ?, NULL, NULL, ?)",
            (mahlzeit_id, lebensmittel_id, float(menge_g), zuordnung_weg),
        )
    return cursor.lastrowid


def position_loeschen(position_id: int) -> None:
    """Löscht eine einzelne Position und räumt eine leer gewordene Mahlzeit weg."""
    with verbindung() as con:
        eintrag = con.execute(
            "SELECT mahlzeit_id FROM mahlzeit_position WHERE position_id = ?",
            (position_id,),
        ).fetchone()
        if eintrag is None:
            return

        con.execute("DELETE FROM mahlzeit_position WHERE position_id = ?", (position_id,))
        rest = con.execute(
            "SELECT COUNT(*) AS anzahl FROM mahlzeit_position WHERE mahlzeit_id = ?",
            (eintrag["mahlzeit_id"],),
        ).fetchone()["anzahl"]
        if rest == 0:
            con.execute("DELETE FROM mahlzeit WHERE mahlzeit_id = ?", (eintrag["mahlzeit_id"],))


# --------------------------------------------------------------------------- #
# Tagesaktivität, Sport und Tagesbedarf
# --------------------------------------------------------------------------- #
def tag_aktivitaet(profil_id: int, datum: date) -> sqlite3.Row | None:
    """Haltungsanteile eines Tages. None bedeutet: für den Tag nichts erfasst."""
    with verbindung() as con:
        return con.execute(
            "SELECT * FROM tag_aktivitaet WHERE profil_id = ? AND datum = ?",
            (profil_id, datum.isoformat()),
        ).fetchone()


def tag_aktivitaet_speichern(
    profil_id: int,
    datum: date,
    min_schlaf: int,
    min_sitzend: int,
    min_stehend: int,
    min_veranstaltung: int,
    tagestyp: str | None,
) -> None:
    minuten = (int(min_schlaf), int(min_sitzend), int(min_stehend), int(min_veranstaltung))
    if any(wert < 0 for wert in minuten):
        raise DatenFehler("Minuten können nicht negativ sein.")
    if sum(minuten) > berechnung.MINUTEN_JE_TAG:
        raise DatenFehler(
            "Schlaf und Arbeit ergeben zusammen mehr als 24 Stunden."
        )
    if tagestyp is not None and tagestyp not in berechnung.TAGESTYPEN:
        raise DatenFehler(f"Unbekannter Tagestyp: {tagestyp!r}")

    with verbindung() as con:
        con.execute(
            "INSERT INTO tag_aktivitaet (profil_id, datum, min_schlaf, min_sitzend, "
            "min_stehend, min_veranstaltung, tagestyp) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (profil_id, datum) DO UPDATE SET min_schlaf = excluded.min_schlaf, "
            "min_sitzend = excluded.min_sitzend, min_stehend = excluded.min_stehend, "
            "min_veranstaltung = excluded.min_veranstaltung, tagestyp = excluded.tagestyp",
            (profil_id, datum.isoformat(), *minuten, tagestyp),
        )


def tag_aktivitaet_loeschen(profil_id: int, datum: date) -> None:
    """Löscht den Tageseintrag und den daraus abgeleiteten Bedarf."""
    with verbindung() as con:
        con.execute(
            "DELETE FROM tag_aktivitaet WHERE profil_id = ? AND datum = ?",
            (profil_id, datum.isoformat()),
        )
        con.execute(
            "DELETE FROM tagesbedarf WHERE profil_id = ? AND datum = ?",
            (profil_id, datum.isoformat()),
        )


def met_grundwerte() -> dict[str, sqlite3.Row]:
    """MET-Grundwerte aus import_met_grundwerte.py, Schlüssel -> Zeile.

    Einzige Quelle für die MET-Werte von Schlaf, Arbeit und Restzeit. Im Code
    stehen keine.
    """
    with verbindung() as con:
        try:
            zeilen = con.execute(
                "SELECT schluessel, name, met, code, quelle FROM met_grundwert"
            ).fetchall()
        except sqlite3.OperationalError:
            return {}
    return {zeile["schluessel"]: zeile for zeile in zeilen}


def sportarten(kategorie: str | None = None) -> list[sqlite3.Row]:
    """Katalog aus import_sportarten.py. Leer, wenn der Import noch nicht lief."""
    bedingung = "WHERE kategorie = ? " if kategorie else ""
    werte = (kategorie,) if kategorie else ()
    with verbindung() as con:
        try:
            return con.execute(
                "SELECT sportart_id, code, name, met_wert, kategorie FROM sportart "
                f"{bedingung}ORDER BY met_wert, name",
                werte,
            ).fetchall()
        except sqlite3.OperationalError:
            return []


def sportkategorien() -> list[str]:
    with verbindung() as con:
        try:
            return [
                zeile["kategorie"]
                for zeile in con.execute(
                    "SELECT DISTINCT kategorie FROM sportart "
                    "WHERE kategorie IS NOT NULL ORDER BY kategorie"
                )
            ]
        except sqlite3.OperationalError:
            return []


def sporteinheiten(profil_id: int, datum: date) -> list[sqlite3.Row]:
    with verbindung() as con:
        try:
            return con.execute(
                "SELECT e.einheit_id, e.dauer_min, s.name, s.met_wert "
                "FROM sporteinheit e JOIN sportart s ON s.sportart_id = e.sportart_id "
                "WHERE e.profil_id = ? AND e.datum = ? ORDER BY e.einheit_id",
                (profil_id, datum.isoformat()),
            ).fetchall()
        except sqlite3.OperationalError:
            return []


def sporteinheit_hinzufuegen(
    profil_id: int, datum: date, sportart_id: int, dauer_min: int
) -> int:
    if dauer_min <= 0:
        raise DatenFehler("Die Dauer muss größer als 0 Minuten sein.")
    with verbindung() as con:
        cursor = con.execute(
            "INSERT INTO sporteinheit (profil_id, datum, sportart_id, dauer_min) "
            "VALUES (?, ?, ?, ?)",
            (profil_id, datum.isoformat(), sportart_id, int(dauer_min)),
        )
    return cursor.lastrowid


def sporteinheit_loeschen(einheit_id: int) -> None:
    with verbindung() as con:
        con.execute("DELETE FROM sporteinheit WHERE einheit_id = ?", (einheit_id,))


def gewicht_bis(profil_id: int, datum: date) -> sqlite3.Row | None:
    """Zuletzt bekanntes Gewicht vor oder an diesem Datum."""
    with verbindung() as con:
        return con.execute(
            "SELECT datum, gewicht_kg FROM gewicht WHERE profil_id = ? AND datum <= ? "
            "ORDER BY datum DESC LIMIT 1",
            (profil_id, datum.isoformat()),
        ).fetchone()


def tagesbedarf(profil_id: int, datum: date) -> dict:
    """Tagesbedarf eines Tages, immer frisch gerechnet und dann festgehalten.

    Der gespeicherte Wert kann so nicht veralten: jeder Lesezugriff rechnet aus
    Gewicht, Aktivität und Sporteinheiten neu und schreibt das Ergebnis mit
    neuem berechnet_am zurück. Ändert sich später eines der drei, ist der Wert
    beim nächsten Lesen bereits angepasst.

    Rückgabe ist immer ein dict mit:
      status       ok | kein_profil | kind | keine_aktivitaet | kein_gewicht |
                   met_fehlt | restzeit_negativ
      zeile        die Zeile aus tagesbedarf, nur bei status ok
      bloecke      die Blöcke des Tages, zusammen immer 1440 Minuten
      restzeit_min berechnete Restzeit, negativ heißt: mehr als 24 Stunden erfasst
      fehlende_met Schlüssel, die in met_grundwert fehlen

    Außer bei status ok wird eine früher gespeicherte Zeile entfernt, damit kein
    veralteter Wert stehen bleibt.
    """
    eintrag = profil(profil_id)
    aktivitaet = tag_aktivitaet(profil_id, datum)
    gewicht = gewicht_bis(profil_id, datum)
    met_werte = met_grundwerte()
    fehlende_met = [
        schluessel
        for schluessel in (*berechnung.ERFASSTE_BLOECKE.values(), berechnung.REST_SCHLUESSEL)
        if schluessel not in met_werte
    ]

    grund = None
    if eintrag is None:
        grund = "kein_profil"
    elif eintrag["typ"] != "erwachsen":
        grund = "kind"
    elif aktivitaet is None:
        grund = "keine_aktivitaet"
    elif gewicht is None:
        grund = "kein_gewicht"
    elif fehlende_met:
        grund = "met_fehlt"

    if grund is not None:
        return _bedarf_verwerfen(profil_id, datum, grund, fehlende_met=fehlende_met)

    gewicht_kg = gewicht["gewicht_kg"]
    bloecke = berechnung.tagesbloecke(
        minuten={feld: aktivitaet[feld] for feld in berechnung.ERFASSTE_BLOECKE},
        sporteinheiten=[
            (einheit["name"], einheit["met_wert"], einheit["dauer_min"])
            for einheit in sporteinheiten(profil_id, datum)
        ],
        met_werte={schluessel: zeile["met"] for schluessel, zeile in met_werte.items()},
        gewicht_kg=gewicht_kg,
    )

    restzeit = berechnung.restzeit_minuten(bloecke)
    if restzeit < 0:
        return _bedarf_verwerfen(profil_id, datum, "restzeit_negativ", bloecke=bloecke)

    grundumsatz = berechnung.grundumsatz_kcal(
        geschlecht=eintrag["geschlecht"],
        gewicht_kg=gewicht_kg,
        groesse_cm=eintrag["groesse_cm"],
        alter_jahre=berechnung.alter_in_jahren(date.fromisoformat(eintrag["geburtsdatum"]), datum),
    )
    # Alles außer Sport zählt als Aktivitätsanteil: Schlaf, Arbeit und Restzeit.
    aktivitaet_anteil = berechnung.summe_kcal(bloecke, ("schlaf", "arbeit", "rest"))
    sport_anteil = berechnung.summe_kcal(bloecke, ("sport",))
    bedarf = grundumsatz + aktivitaet_anteil + sport_anteil

    with verbindung() as con:
        con.execute(
            "INSERT INTO tagesbedarf (profil_id, datum, gewicht_kg_verwendet, "
            "grundumsatz_kcal, aktivitaet_kcal, sport_kcal, bedarf_kcal, berechnet_am) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (profil_id, datum) DO UPDATE SET "
            "gewicht_kg_verwendet = excluded.gewicht_kg_verwendet, "
            "grundumsatz_kcal = excluded.grundumsatz_kcal, "
            "aktivitaet_kcal = excluded.aktivitaet_kcal, "
            "sport_kcal = excluded.sport_kcal, bedarf_kcal = excluded.bedarf_kcal, "
            "berechnet_am = excluded.berechnet_am",
            (
                profil_id,
                datum.isoformat(),
                gewicht_kg,
                grundumsatz,
                aktivitaet_anteil,
                sport_anteil,
                bedarf,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        zeile = con.execute(
            "SELECT * FROM tagesbedarf WHERE profil_id = ? AND datum = ?",
            (profil_id, datum.isoformat()),
        ).fetchone()

    return {
        "status": "ok",
        "zeile": zeile,
        "bloecke": bloecke,
        "restzeit_min": restzeit,
        "fehlende_met": [],
    }


def _bedarf_verwerfen(
    profil_id: int,
    datum: date,
    grund: str,
    bloecke: list[dict] | None = None,
    fehlende_met: list[str] | None = None,
) -> dict:
    """Entfernt einen früher gespeicherten Bedarf und meldet den Grund zurück."""
    with verbindung() as con:
        con.execute(
            "DELETE FROM tagesbedarf WHERE profil_id = ? AND datum = ?",
            (profil_id, datum.isoformat()),
        )
    return {
        "status": grund,
        "zeile": None,
        "bloecke": bloecke or [],
        "restzeit_min": berechnung.restzeit_minuten(bloecke) if bloecke else None,
        "fehlende_met": fehlende_met or [],
    }


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
