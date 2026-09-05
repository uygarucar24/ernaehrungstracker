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


# Einstufung der Zufuhr gegenüber dem Referenzwert. Die Anwendung spricht
# ausschließlich von Abweichungen vom Referenzwert, nie von Mangel oder
# Versorgung, und gibt keine Ernährungsempfehlung.
UNTERHALB = "unterhalb"
IM_BEREICH = "im_bereich"
OBERHALB = "oberhalb"
KEINE_AUSSAGE = "keine_aussage"

EINSTUFUNG_ANZEIGE = {
    UNTERHALB: "unterhalb des Referenzwerts",
    IM_BEREICH: "im Bereich",
    OBERHALB: "oberhalb der Obergrenze",
    KEINE_AUSSAGE: "keine Aussage möglich",
}


def einstufung(
    zufuhr: float | None,
    referenz: float | None,
    obergrenze: float | None,
    abdeckung: float,
) -> str:
    """Vergleicht die Zufuhr mit dem Referenzwert.

    abdeckung ist die Menge in Gramm, für die ein Wert vorliegt. Ist sie null,
    liegt für keine Position ein Wert vor und es ist keine Aussage möglich, auch
    nicht "unterhalb des Referenzwerts". Dasselbe gilt ohne Referenzwert. Ist nur
    eine Obergrenze hinterlegt, entfällt die Einstufung "unterhalb": ohne
    Referenzwert gibt es keine Untergrenze.
    """
    if abdeckung <= 0 or zufuhr is None or (referenz is None and obergrenze is None):
        return KEINE_AUSSAGE
    if obergrenze is not None and zufuhr > obergrenze:
        return OBERHALB
    if referenz is not None and zufuhr < referenz:
        return UNTERHALB
    return IM_BEREICH


def referenz_je_gewicht(referenz: float | None, bezug: str, gewicht_kg: float | None):
    """Rechnet einen Referenzwert mit Bezug je_kg auf das Gewicht um.

    Ohne bekanntes Gewicht bleibt der Wert unbestimmt, es wird nichts geschätzt.
    """
    if referenz is None or bezug != "je_kg":
        return referenz
    return None if gewicht_kg is None else referenz * gewicht_kg


# Prüfung auf Unverträglichkeiten. Beschrieben wird ausschließlich, was im
# Datenbestand steht; es wird nie eine Verträglichkeit zugesichert.
ENTHALTEN = "enthalten"
UNTER_SCHWELLE = "unter_schwelle"
FREI_LOGISCH = "frei_logisch"
FREI_ANDERE = "frei_andere"
OHNE_ANGABE = "ohne_angabe"

# Herkunft im BLS, die eine echte Null bedeutet: der Stoff kommt nicht vor.
LOGISCHE_NULL = "Logische Null"


def unvertraeglichkeit_zustand(
    wert_je_100g: float | None, herkunft: str | None, schwelle_je_100g: float | None = None
) -> str:
    """Beurteilt eine Position anhand des Nährwerts und seiner Herkunft.

    Ohne Zeile in naehrwert gibt es keine Angabe. Das ist ausdrücklich keine
    Entwarnung und wird nicht wie ein Nullwert behandelt.

    Ohne hinterlegte Schwelle löst jede nachgewiesene Menge einen Hinweis aus,
    weil die individuelle Empfindlichkeit stark schwankt. Ist eine Schwelle
    hinterlegt, gilt sie als Grenze.
    """
    if wert_je_100g is None:
        return OHNE_ANGABE
    if wert_je_100g > (schwelle_je_100g or 0):
        return ENTHALTEN
    if wert_je_100g > 0:
        return UNTER_SCHWELLE
    return FREI_LOGISCH if (herkunft or "").strip() == LOGISCHE_NULL else FREI_ANDERE


def menge_je_portion(wert_je_100g: float, menge_g: float, bezugsmenge_g: float) -> float:
    """Rechnet einen Wert je Bezugsmenge auf die Portion um."""
    return wert_je_100g * menge_g / bezugsmenge_g


def naehrwertsummen(
    positionen: list[tuple[int, float]],
    werte: dict[tuple[int, str], float],
    codes: tuple[str, ...],
    bezugsmenge_g: float,
) -> tuple[dict[str, float], dict[str, float], float]:
    """Summiert Nährwerte über Positionen und misst, worauf die Summe beruht.

    positionen: (lebensmittel_id, menge_g). werte: (lebensmittel_id, code) -> Wert
    je Bezugsmenge; fehlt der Schlüssel, ist der Wert unbekannt und geht nicht
    als 0 in die Summe ein.

    Gibt (Summen, Abdeckung, Gesamtmenge) zurück. Die Abdeckung ist je Nährstoff
    die Menge in Gramm, für die ein Wert vorliegt, nicht die Zahl der Positionen:
    200 Gramm ohne Nährwert wiegen für die Aussagekraft einer Summe schwerer als
    5 Gramm. Ein ausdrücklich erfasster Nullwert zählt als vorhanden, weil dazu
    eine Zeile in naehrwert steht.
    """
    summen = {code: 0.0 for code in codes}
    abdeckung = {code: 0.0 for code in codes}
    gesamtmenge = 0.0
    for lebensmittel_id, menge_g in positionen:
        gesamtmenge += menge_g
        for code in codes:
            wert = werte.get((lebensmittel_id, code))
            if wert is None:
                continue
            summen[code] += wert * menge_g / bezugsmenge_g
            abdeckung[code] += menge_g
    return summen, abdeckung, gesamtmenge


def abdeckung_anteil(menge_mit_wert: float, menge_gesamt: float) -> float | None:
    """Anteil der erfassten Menge mit vorhandenem Wert, 0 bis 1.

    Ohne erfasste Menge gibt es keinen Anteil; dann ist nichts zu berechnen.
    """
    if not menge_gesamt:
        return None
    return menge_mit_wert / menge_gesamt


def abdeckungstext(menge_mit_wert: float, menge_gesamt: float, kurz: bool = False) -> str:
    """Formuliert die Abdeckung als Mengenanteil, nicht als Zahl der Lebensmittel.

    Gerundet wird auf ganze Prozent. 100 Prozent erscheinen nur bei tatsächlich
    lückenloser Abdeckung und 0 Prozent nur, wenn wirklich kein Wert vorliegt:
    eine gerundete Anzeige darf eine Lücke nicht verschwinden lassen.
    """
    anteil = abdeckung_anteil(menge_mit_wert, menge_gesamt)
    if anteil is None:
        return "keine erfasste Menge"

    prozent = round(anteil * 100)
    if prozent == 100 and menge_mit_wert < menge_gesamt:
        prozent = 99
    if prozent == 0 and menge_mit_wert > 0:
        prozent = 1

    if kurz:
        return f"{prozent} % ({_gramm(menge_mit_wert)})"
    return (
        f"{prozent} % der erfassten Menge, {_gramm(menge_mit_wert)} von "
        f"{_gramm(menge_gesamt)}"
    )


def _gramm(wert: float) -> str:
    """Ganze Gramm, mit Nachkommastelle nur dort, wo sie einen Unterschied macht.

    Sonst stünde neben "99 %" zweimal dieselbe gerundete Menge.
    """
    return f"{wert:.0f} g" if abs(wert - round(wert)) < 0.05 else f"{wert:.1f} g"
