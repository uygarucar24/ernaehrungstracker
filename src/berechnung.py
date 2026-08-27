"""Berechnung von Alter, Grundumsatz, Tagesblöcken und Kalorienziel.

Reine Funktionen ohne Datenbankzugriff, damit sie einzeln nachrechenbar sind.
Es stehen hier bewusst keine MET-Werte: die kommen ausschließlich aus der
Tabelle met_grundwert (Datei daten/met_grundwerte.csv) und aus sportart.
"""
from __future__ import annotations

from datetime import date

MINUTEN_JE_TAG = 24 * 60

# Erfasste Zeitblöcke: Feld in tag_aktivitaet -> Schlüssel in met_grundwert.
ERFASSTE_BLOECKE = {
    "min_schlaf": "schlaf",
    "min_sitzend": "sitzend",
    "min_stehend": "stehend",
    "min_veranstaltung": "veranstaltung",
}

# Schlüssel des berechneten Restblocks.
REST_SCHLUESSEL = "alltag"

# Tagestypen belegen die Arbeitszeiten vor, änderbar bleiben sie trotzdem.
TAGESTYPEN = {
    "homeoffice": {"min_sitzend": 420, "min_stehend": 60, "min_veranstaltung": 0},
    "buero": {"min_sitzend": 240, "min_stehend": 240, "min_veranstaltung": 0},
    "veranstaltung": {"min_sitzend": 0, "min_stehend": 0, "min_veranstaltung": 480},
    "frei": {"min_sitzend": 0, "min_stehend": 0, "min_veranstaltung": 0},
}

TAGESTYP_ANZEIGE = {
    "homeoffice": "Homeoffice",
    "buero": "Büro",
    "veranstaltung": "Veranstaltung",
    "frei": "frei",
}

# Ein Kilogramm Körpergewicht entspricht rund 7000 kcal.
KCAL_JE_KG = 7000.0


def alter_in_jahren(geburtsdatum: date, stichtag: date | None = None) -> int:
    """Alter wird berechnet, nicht gespeichert."""
    stichtag = stichtag or date.today()
    vorbei = (stichtag.month, stichtag.day) < (geburtsdatum.month, geburtsdatum.day)
    return stichtag.year - geburtsdatum.year - int(vorbei)


def grundumsatz_kcal(
    geschlecht: str, gewicht_kg: float, groesse_cm: float, alter_jahre: int
) -> float:
    """Grundumsatz nach Mifflin-St Jeor.

    Männer: 10 x Gewicht + 6,25 x Größe - 5 x Alter + 5
    Frauen:  10 x Gewicht + 6,25 x Größe - 5 x Alter - 161
    """
    basis = 10 * gewicht_kg + 6.25 * groesse_cm - 5 * alter_jahre
    return basis + 5 if geschlecht == "m" else basis - 161


def mehrverbrauch_kcal(met: float, gewicht_kg: float, dauer_min: float) -> float:
    """(MET - 1) x Gewicht x Stunden.

    Der Abzug von 1 MET ist zwingend: der Ruheumsatz steckt bereits im
    Grundumsatz. Ohne den Abzug würde die Zeit doppelt gezählt.
    """
    return (met - 1) * gewicht_kg * (dauer_min / 60.0)


def tagesbloecke(
    minuten: dict[str, int],
    sporteinheiten: list[tuple[str, float, int]],
    met_werte: dict[str, float],
    gewicht_kg: float,
) -> list[dict]:
    """Teilt den Tag vollständig in Blöcke auf und rechnet jeden einzeln.

    minuten: Werte aus tag_aktivitaet je Feld aus ERFASSTE_BLOECKE.
    sporteinheiten: (Name, MET, Dauer in Minuten).
    met_werte: Schlüssel -> MET aus met_grundwert.

    Die Restzeit wird nicht erfasst, sondern als 1440 minus Schlaf minus Arbeit
    minus Sport berechnet. Sie kann negativ werden; dann ergeben die erfassten
    Zeiten zusammen mehr als 24 Stunden und der Aufrufer gibt keinen Bedarf aus.

    Es entstehen nur Blöcke für Felder, die in minuten stehen. Kinderprofile
    übergeben deshalb ausschließlich min_schlaf, und die Arbeitsblöcke entfallen
    ganz, statt mit 0 Minuten mitzulaufen.
    """
    bloecke = []
    for feld, schluessel in ERFASSTE_BLOECKE.items():
        if feld not in minuten:
            continue
        dauer = int(minuten.get(feld) or 0)
        met = met_werte[schluessel]
        bloecke.append(
            {
                "art": "schlaf" if schluessel == "schlaf" else "arbeit",
                "schluessel": schluessel,
                "minuten": dauer,
                "met": met,
                "kcal": mehrverbrauch_kcal(met, gewicht_kg, dauer),
            }
        )

    for name, met, dauer in sporteinheiten:
        bloecke.append(
            {
                "art": "sport",
                "schluessel": name,
                "minuten": int(dauer),
                "met": met,
                "kcal": mehrverbrauch_kcal(met, gewicht_kg, int(dauer)),
            }
        )

    verplant = sum(block["minuten"] for block in bloecke)
    rest = MINUTEN_JE_TAG - verplant
    met_rest = met_werte[REST_SCHLUESSEL]
    bloecke.append(
        {
            "art": "rest",
            "schluessel": REST_SCHLUESSEL,
            "minuten": rest,
            "met": met_rest,
            "kcal": mehrverbrauch_kcal(met_rest, gewicht_kg, rest),
        }
    )
    return bloecke


def restzeit_minuten(bloecke: list[dict]) -> int:
    """Minuten des berechneten Restblocks."""
    return next(block["minuten"] for block in bloecke if block["art"] == "rest")


def summe_kcal(bloecke: list[dict], arten: tuple[str, ...]) -> float:
    return sum(block["kcal"] for block in bloecke if block["art"] in arten)


def kalorienziel_kcal(bedarf_kcal: float, aenderung_kg_woche: float) -> float:
    """Bedarf plus die tägliche Differenz aus der gewünschten Wochenänderung."""
    return bedarf_kcal + aenderung_kg_woche * KCAL_JE_KG / 7
