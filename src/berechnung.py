"""Berechnung von Alter, Grundumsatz, Mehrverbrauch und Kalorienziel.

Reine Funktionen ohne Datenbankzugriff, damit sie einzeln nachrechenbar sind.
"""
from __future__ import annotations

from datetime import date

# MET-Werte der drei Haltungsanteile. Sie überschneiden sich nicht und ergeben
# zusammen die Arbeitszeit.
HALTUNG_MET = {
    "min_sitzend": 1.3,
    "min_stehend": 1.8,
    "min_veranstaltung": 4.0,
}

HALTUNG_ANZEIGE = {
    "min_sitzend": "Sitzend",
    "min_stehend": "Stehend",
    "min_veranstaltung": "Veranstaltung",
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


def aktivitaet_kcal(minuten_je_haltung: dict[str, float], gewicht_kg: float) -> float:
    """Summe des Mehrverbrauchs über die drei Haltungsanteile."""
    return sum(
        mehrverbrauch_kcal(HALTUNG_MET[feld], gewicht_kg, minuten or 0)
        for feld, minuten in minuten_je_haltung.items()
    )


def kalorienziel_kcal(bedarf_kcal: float, aenderung_kg_woche: float) -> float:
    """Bedarf plus die tägliche Differenz aus der gewünschten Wochenänderung."""
    return bedarf_kcal + aenderung_kg_woche * KCAL_JE_KG / 7
