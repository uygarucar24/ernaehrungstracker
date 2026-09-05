"""Datenexport: die erfassten Daten eines Zeitraums als CSV-Dateien in einem ZIP.

Reine Datenausgabe. Der Export enthält keine Einstufungen, keine Bewertungen und
keine Empfehlungen; er gibt aus, was erfasst und was daraus berechnet wurde.

Zwei Regeln bestimmen den Aufbau:

* **Leer ist nicht null.** Fehlt eine Zeile in ``naehrwert``, bleibt das Feld leer.
  Ein Tag ohne Eintrag in ``tag_aktivitaet`` hat keinen Tagesbedarf und bekommt
  leere Felder, nicht die Zahl 0. In einer Tabellenkalkulation entstünde sonst
  genau die Verwechslung, die die Anwendung vermeidet.
* **Herkunft mitführen.** Zu jedem Nährwert steht der Quellencode aus
  ``naehrwert.wert_herkunft`` daneben, je Lebensmittel zusätzlich, ob es aus dem
  Bundeslebensmittelschlüssel stammt oder selbst erfasst wurde.

Kinderprofile: keine Kalorienbilanz und keine Zielwerte. Die Datei zum
Tagesbedarf wird nicht erzeugt und die Energiespalte der Aktivität nicht
aufgebaut, weil für Kinderprofile kein Bedarf gerechnet wird.
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import date, datetime

from . import berechnung, datenbank

# UTF-8 mit BOM, sonst zerlegt Excel die Umlaute.
KODIERUNG = "utf-8-sig"
# Komma als Feldtrennzeichen und Punkt als Dezimaltrennzeichen gehören zusammen;
# gemischt ließe sich die Datei nicht mehr eindeutig lesen.
TRENNZEICHEN = ","
ZEILENENDE = "\r\n"

# Nährwerte werden mit dieser Genauigkeit geschrieben. Gerundet wird erst hier,
# nicht vorher: eine in der Tabellenkalkulation neu gebildete Tagessumme muss
# mit der Anzeige übereinstimmen.
NACHKOMMASTELLEN = 3

DATEI_RAHMEN = "rahmenangaben.csv"
DATEI_MAHLZEITEN = "mahlzeitenpositionen.csv"
DATEI_AKTIVITAET = "aktivitaet_und_sport.csv"
DATEI_GEWICHT = "gewicht.csv"
DATEI_BEDARF = "tagesbedarf.csv"

LEBENSMITTEL_HERKUNFT = {
    "bls": "Bundeslebensmittelschlüssel",
    "eigen": "selbst erfasst",
}

# Feste Quellenangaben. Stand und Bezeichnung der Referenzwerte kommen, soweit
# vorhanden, aus der Datenbank.
QUELLE_BLS = "Bundeslebensmittelschlüssel 4.0, Max Rubner-Institut, Ausgabe 2025"
QUELLE_MET = "Compendium of Physical Activities 2024"
QUELLE_DGE = "DGE/ÖGE-Referenzwerte für die Nährstoffzufuhr, 3. Auflage, 1. Ausgabe 2025"


# --------------------------------------------------------------------------- #
# Formatierung
# --------------------------------------------------------------------------- #
def _zahl(wert: float | None, stellen: int = NACHKOMMASTELLEN) -> str:
    """Zahl mit Punkt als Dezimaltrennzeichen. None wird zum leeren Feld."""
    if wert is None:
        return ""
    text = f"{float(wert):.{stellen}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _ganz(wert: int | None) -> str:
    return "" if wert is None else str(int(wert))


def _text(wert: object) -> str:
    return "" if wert is None else str(wert)


def _csv(kopf: list[str], zeilen: list[list[str]]) -> str:
    puffer = io.StringIO()
    schreiber = csv.writer(
        puffer, delimiter=TRENNZEICHEN, lineterminator=ZEILENENDE, quoting=csv.QUOTE_MINIMAL
    )
    schreiber.writerow(kopf)
    schreiber.writerows(zeilen)
    return puffer.getvalue()


def _spaltenname(zeile) -> str:
    """Code, Name und Einheit im Kopf, damit die Spalte für sich lesbar ist."""
    return f"{zeile['bls_spalte']} {zeile['name']} ({zeile['einheit']})"


def dateiname(profilname: str, von: date, bis: date) -> str:
    kurz = re.sub(r"[^A-Za-z0-9]+", "_", profilname).strip("_") or "profil"
    return f"export_{kurz}_{von.isoformat()}_bis_{bis.isoformat()}.zip"


# --------------------------------------------------------------------------- #
# Mahlzeitenpositionen
# --------------------------------------------------------------------------- #
def _mahlzeiten(profil_id: int, von: date, bis: date, naehrstoffe: list) -> tuple[str, int]:
    """Eine Zeile je Position, je Nährstoff eine Wert- und eine Herkunftsspalte.

    Ausgegeben wird der auf die erfasste Menge umgerechnete Wert, also genau
    das, was die Anwendung anzeigt. Fehlt die Zeile in naehrwert, bleiben beide
    Spalten leer.
    """
    positionen = datenbank.positionen_zeitraum(profil_id, von, bis)
    reihenfolge = {abschnitt: nr for nr, abschnitt in enumerate(datenbank.TAGESABSCHNITTE)}
    positionen = sorted(
        positionen,
        key=lambda zeile: (
            zeile["datum"],
            reihenfolge.get(zeile["tagesabschnitt"], len(reihenfolge)),
            zeile["position_id"],
        ),
    )

    codes = tuple(zeile["bls_spalte"] for zeile in naehrstoffe)
    werte = datenbank.naehrwerte_mit_herkunft(
        [zeile["lebensmittel_id"] for zeile in positionen], codes
    )

    kopf = [
        "datum",
        "tagesabschnitt",
        "mahlzeit",
        "position_id",
        "uhrzeit",
        "lebensmittel",
        "hersteller",
        "lebensmittel_herkunft",
        "bls_schluessel",
        "menge_g",
    ]
    for zeile in naehrstoffe:
        kopf.append(_spaltenname(zeile))
        kopf.append(f"{zeile['bls_spalte']} Herkunft")

    zeilen = []
    for position in positionen:
        eintrag = [
            position["datum"],
            position["tagesabschnitt"],
            datenbank.TAGESABSCHNITT_ANZEIGE.get(
                position["tagesabschnitt"], position["tagesabschnitt"]
            ),
            _ganz(position["position_id"]),
            _text(position["uhrzeit"]),
            _text(position["bezeichnung"]),
            _text(position["hersteller"]),
            LEBENSMITTEL_HERKUNFT.get(position["herkunft"], _text(position["herkunft"])),
            _text(position["bls_schluessel"]),
            _zahl(position["menge_g"], 1),
        ]
        for naehrstoff in naehrstoffe:
            quelle = werte.get((position["lebensmittel_id"], naehrstoff["bls_spalte"]))
            if quelle is None:
                # Keine Zeile in naehrwert: unbekannt. Kein Wert, keine 0.
                eintrag.extend(["", ""])
                continue
            eintrag.append(
                _zahl(
                    berechnung.menge_je_portion(
                        quelle["wert_je_100g"], position["menge_g"], datenbank.BEZUGSMENGE_G
                    )
                )
            )
            eintrag.append(_text(quelle["wert_herkunft"]))
        zeilen.append(eintrag)

    return _csv(kopf, zeilen), len(zeilen)


# --------------------------------------------------------------------------- #
# Aktivität und Sport
# --------------------------------------------------------------------------- #
def _block(
    art: str,
    bezeichnung: str,
    minuten: int,
    met: float | None,
    met_quelle: str | None,
    angabe: str,
    gewicht_kg: float | None,
) -> dict:
    """Ein Zeitblock des Tages. Ohne MET oder ohne Gewicht bleibt kcal leer."""
    kcal = (
        berechnung.mehrverbrauch_kcal(met, gewicht_kg, minuten)
        if met is not None and gewicht_kg is not None
        else None
    )
    return {
        "art": art,
        "bezeichnung": bezeichnung,
        "minuten": int(minuten),
        "met": met,
        "met_quelle": met_quelle,
        "angabe": angabe,
        "kcal": kcal,
    }


def _bloecke(
    aktivitaet, einheiten: list, met_werte: dict, ist_kind: bool, gewicht_kg: float | None
) -> list[dict]:
    """Die Blöcke eines Tages in der Reihenfolge der Anwendung.

    Ohne Eintrag in tag_aktivitaet ist der Tag nicht vollständig aufgeteilt;
    dann entsteht keine Restzeit, weil Schlaf und Arbeit fehlen.

    Kinderprofil: nur Schlaf, Sport und Restzeit. Arbeitszeit wird dort nicht
    erfasst, also werden auch keine Arbeitsblöcke aufgebaut.
    """
    bloecke: list[dict] = []
    felder = ("min_schlaf",) if ist_kind else tuple(berechnung.ERFASSTE_BLOECKE)

    if aktivitaet is not None:
        for feld in felder:
            schluessel = berechnung.ERFASSTE_BLOECKE[feld]
            grundwert = met_werte.get(schluessel)
            bloecke.append(
                _block(
                    "schlaf" if schluessel == "schlaf" else "arbeit",
                    grundwert["name"] if grundwert is not None else schluessel,
                    int(aktivitaet[feld] or 0),
                    grundwert["met"] if grundwert is not None else None,
                    grundwert["quelle"] if grundwert is not None else None,
                    "erfasst",
                    gewicht_kg,
                )
            )

    for einheit in einheiten:
        bloecke.append(
            _block(
                "sport",
                einheit["name"],
                einheit["dauer_min"],
                einheit["met_wert"],
                einheit["quelle"],
                "erfasst",
                gewicht_kg,
            )
        )

    if aktivitaet is not None:
        grundwert = met_werte.get(berechnung.REST_SCHLUESSEL)
        rest = berechnung.MINUTEN_JE_TAG - sum(block["minuten"] for block in bloecke)
        bloecke.append(
            _block(
                "restzeit",
                grundwert["name"] if grundwert is not None else berechnung.REST_SCHLUESSEL,
                rest,
                grundwert["met"] if grundwert is not None else None,
                grundwert["quelle"] if grundwert is not None else None,
                "berechnet",
                gewicht_kg,
            )
        )
    return bloecke


def _aktivitaet(profil_id: int, von: date, bis: date, ist_kind: bool) -> tuple[str, int]:
    """Eine Zeile je Zeitblock und Tag: Schlaf, Arbeit, Sporteinheiten, Restzeit."""
    tage = {zeile["datum"]: zeile for zeile in datenbank.tagesaktivitaeten(profil_id, von, bis)}
    einheiten: dict[str, list] = {}
    for zeile in datenbank.sporteinheiten_zeitraum(profil_id, von, bis):
        einheiten.setdefault(zeile["datum"], []).append(zeile)
    met_werte = datenbank.met_grundwerte()

    kopf = [
        "datum",
        "tagestyp",
        "block",
        "bezeichnung",
        "minuten",
        "minuten_angabe",
        "met",
        "met_quelle",
    ]
    # Kinderprofil: keine Energieangaben, weil kein Tagesbedarf gerechnet wird.
    if not ist_kind:
        kopf.append("mehrverbrauch_kcal")

    zeilen = []
    for tag in sorted(set(tage) | set(einheiten)):
        aktivitaet = tage.get(tag)
        gewicht = None if ist_kind else datenbank.gewicht_bis(profil_id, date.fromisoformat(tag))
        for block in _bloecke(
            aktivitaet,
            einheiten.get(tag, []),
            met_werte,
            ist_kind,
            gewicht["gewicht_kg"] if gewicht is not None else None,
        ):
            eintrag = [
                tag,
                _text(aktivitaet["tagestyp"]) if aktivitaet is not None else "",
                block["art"],
                block["bezeichnung"],
                _ganz(block["minuten"]),
                block["angabe"],
                _zahl(block["met"], 2),
                _text(block["met_quelle"]),
            ]
            if not ist_kind:
                eintrag.append(_zahl(block["kcal"], 1))
            zeilen.append(eintrag)

    return _csv(kopf, zeilen), len(zeilen)


# --------------------------------------------------------------------------- #
# Gewicht
# --------------------------------------------------------------------------- #
def _gewicht(profil_id: int, von: date, bis: date) -> tuple[str, int]:
    """Nur Tage mit Eintrag. Tage ohne Messung bleiben leer, es wird nichts ergänzt."""
    zeilen = [
        [zeile["datum"], _zahl(zeile["gewicht_kg"], 1), _text(zeile["notiz"])]
        for zeile in datenbank.gewichte_zeitraum(profil_id, von, bis)
    ]
    return _csv(["datum", "gewicht_kg", "notiz"], zeilen), len(zeilen)


# --------------------------------------------------------------------------- #
# Tagesbedarf und Bilanz
# --------------------------------------------------------------------------- #
def _bedarfstage(profil_id: int, von: date, bis: date) -> list[str]:
    """Tage mit Aktivität, Sport oder Mahlzeit. Nur dafür kann es einen Bedarf geben."""
    tage = {zeile["datum"] for zeile in datenbank.tagesaktivitaeten(profil_id, von, bis)}
    tage |= {zeile["datum"] for zeile in datenbank.sporteinheiten_zeitraum(profil_id, von, bis)}
    tage |= {zeile["datum"] for zeile in datenbank.positionen_zeitraum(profil_id, von, bis)}
    return sorted(tage)


def _bedarf(profil_id: int, von: date, bis: date) -> tuple[str, int]:
    """Bedarf, Kalorienziel, Aufnahme und Differenz je Tag.

    Ohne Eintrag in tag_aktivitaet gibt es keinen Bedarf: die Felder bleiben
    leer und der Grund steht in der Spalte status. Es wird nicht ersatzweise
    gegen den Grundumsatz oder einen Durchschnitt gerechnet.
    """
    eintrag = datenbank.profil(profil_id)
    rate = eintrag["aenderung_kg_woche"] if eintrag is not None else None
    aufnahme = datenbank.aufnahme_je_tag(profil_id, von, bis)

    kopf = [
        "datum",
        "status",
        "gewicht_kg_verwendet",
        "grundumsatz_kcal",
        "aktivitaet_kcal",
        "sport_kcal",
        "bedarf_kcal",
        "ziel_modus",
        "aenderung_kg_woche",
        "kalorienziel_kcal",
        "aufnahme_kcal",
        "positionen",
        "positionen_mit_energiewert",
        "differenz_kcal",
        "berechnet_am",
    ]

    zeilen = []
    for tag in _bedarfstage(profil_id, von, bis):
        ergebnis = datenbank.tagesbedarf(profil_id, date.fromisoformat(tag))
        zeile = ergebnis["zeile"]
        bedarf = zeile["bedarf_kcal"] if zeile is not None else None
        ziel = None
        if bedarf is not None:
            # Ohne Rate ist das Ziel der Bedarf; bei "halten" sind beide gleich.
            ziel = berechnung.kalorienziel_kcal(bedarf, rate) if rate else bedarf

        tageswerte = aufnahme.get(tag, {})
        positionen = tageswerte.get("positionen", 0)
        energie = tageswerte.get("werte", {}).get("ENERCC")
        # Ohne einen einzigen bekannten Kalorienwert ist die Aufnahme unbekannt.
        # Ausgegeben wird die Zahl der Positionen mit Wert; die Abdeckung als
        # Mengenanteil gehört in die Anzeige, nicht in den Export.
        aufgenommen, mit_wert = (energie[0], energie[2]) if energie else (None, 0)
        differenz = ziel - aufgenommen if ziel is not None and aufgenommen is not None else None

        zeilen.append(
            [
                tag,
                ergebnis["status"],
                _zahl(zeile["gewicht_kg_verwendet"], 1) if zeile is not None else "",
                _zahl(zeile["grundumsatz_kcal"], 1) if zeile is not None else "",
                _zahl(zeile["aktivitaet_kcal"], 1) if zeile is not None else "",
                _zahl(zeile["sport_kcal"], 1) if zeile is not None else "",
                _zahl(bedarf, 1),
                _text(eintrag["ziel_modus"]) if eintrag is not None else "",
                _zahl(rate, 2),
                _zahl(ziel, 1),
                _zahl(aufgenommen, 1),
                _ganz(positionen),
                _ganz(mit_wert),
                _zahl(differenz, 1),
                _text(zeile["berechnet_am"]) if zeile is not None else "",
            ]
        )

    return _csv(kopf, zeilen), len(zeilen)


# --------------------------------------------------------------------------- #
# Rahmenangaben
# --------------------------------------------------------------------------- #
def _rahmenangaben(
    eintrag, von: date, bis: date, umfang: list[tuple[str, str]], ist_kind: bool
) -> str:
    """Profil, Zeitraum, Exportdatum, Dateiliste und die verwendeten Quellen."""
    quelle = datenbank.referenzwert_quelle()
    referenz = (
        f"{quelle['quelle']}, {quelle['stand']}" if quelle is not None else QUELLE_DGE
    )

    zeilen = [
        ["Anwendung", "Ernährungs- und Bewegungstracker"],
        ["Profil", _text(eintrag["name"])],
        ["Profiltyp", _text(eintrag["typ"])],
        ["Zeitraum von", von.isoformat()],
        ["Zeitraum bis", bis.isoformat()],
        ["Exportdatum", datetime.now().isoformat(timespec="seconds")],
        ["Kodierung", "UTF-8 mit BOM"],
        ["Feldtrennzeichen", "Komma"],
        ["Dezimaltrennzeichen", "Punkt"],
        ["Datumsformat", "JJJJ-MM-TT"],
        [
            "Bedeutung leerer Felder",
            "Kein Wert vorhanden. Ein leeres Feld ist nicht als 0 zu lesen.",
        ],
        [
            "Nährwerte",
            "Auf die erfasste Menge umgerechnet, in der Einheit der Spaltenüberschrift. "
            "Je Nährstoff steht daneben die Herkunft des Werts.",
        ],
        [
            "Tage ohne Eintrag",
            "Ein Tag ohne Aktivitätseintrag hat keinen Tagesbedarf; die Felder bleiben "
            "leer und der Grund steht in der Spalte status.",
        ],
    ]
    if ist_kind:
        zeilen.append(
            [
                "Kinderprofil",
                "Ohne Kalorienbilanz und ohne Zielwerte: für Kinderprofile wird kein "
                f"Tagesbedarf berechnet, deshalb gibt es {DATEI_BEDARF} nicht und die "
                "Aktivität wird ohne Energiespalte ausgegeben.",
            ]
        )
    for name, beschreibung in umfang:
        zeilen.append([f"Datei {name}", beschreibung])

    zeilen.append(["Quelle Nährwerte", QUELLE_BLS])
    zeilen.append(["Quelle MET-Werte", QUELLE_MET])
    zeilen.append(["Quelle Referenzwerte", referenz])
    zeilen.append(
        [
            "Hinweis Quellen",
            "Die Referenzwerte werden in der Anwendung für den Vergleich verwendet. "
            "Der Export selbst enthält keine Einstufungen und keine Empfehlungen.",
        ]
    )
    return _csv(["angabe", "wert"], zeilen)


# --------------------------------------------------------------------------- #
# Zusammenstellung
# --------------------------------------------------------------------------- #
def dateien(profil_id: int, von: date, bis: date) -> list[tuple[str, str, str]]:
    """Alle Dateien des Exports als (Dateiname, Inhalt, Beschreibung).

    Die Rahmenangaben stehen am Ende, weil sie die Zeilenzahlen der übrigen
    Dateien nennen.
    """
    eintrag = datenbank.profil(profil_id)
    if eintrag is None:
        raise datenbank.DatenFehler("Das Profil ist nicht vorhanden.")
    if von > bis:
        raise datenbank.DatenFehler("Der Zeitraum beginnt nach seinem Ende.")

    # Ausdrückliche Prüfung des Profiltyps, nicht am leeren Feld entschieden.
    ist_kind = eintrag["typ"] == "kind"
    naehrstoffe = datenbank.alle_naehrstoffe()

    mahlzeiten, anzahl_mahlzeiten = _mahlzeiten(profil_id, von, bis, naehrstoffe)
    aktivitaet, anzahl_aktivitaet = _aktivitaet(profil_id, von, bis, ist_kind)
    gewicht, anzahl_gewicht = _gewicht(profil_id, von, bis)

    umfang = [
        (
            DATEI_MAHLZEITEN,
            f"{anzahl_mahlzeiten} Zeilen, eine je Mahlzeitenposition, mit "
            f"{len(naehrstoffe)} Nährstoffen je Position.",
        ),
        (
            DATEI_AKTIVITAET,
            f"{anzahl_aktivitaet} Zeilen, eine je Zeitblock des Tages: Schlaf, "
            "Arbeit nach Haltung, Sporteinheiten und die berechnete Restzeit.",
        ),
        (DATEI_GEWICHT, f"{anzahl_gewicht} Zeilen, nur Tage mit Eintrag."),
    ]
    inhalte = [
        (DATEI_MAHLZEITEN, mahlzeiten),
        (DATEI_AKTIVITAET, aktivitaet),
        (DATEI_GEWICHT, gewicht),
    ]

    if not ist_kind:
        bedarf, anzahl_bedarf = _bedarf(profil_id, von, bis)
        umfang.append(
            (
                DATEI_BEDARF,
                f"{anzahl_bedarf} Zeilen, eine je Tag mit Aktivität, Sport oder "
                "Mahlzeit, mit Bedarf, Kalorienziel, Aufnahme und Differenz.",
            )
        )
        inhalte.append((DATEI_BEDARF, bedarf))

    rahmen = _rahmenangaben(eintrag, von, bis, umfang, ist_kind)
    beschreibungen = dict(umfang)
    beschreibungen[DATEI_RAHMEN] = "Profil, Zeitraum, Exportdatum und Quellen."

    return [(DATEI_RAHMEN, rahmen, beschreibungen[DATEI_RAHMEN])] + [
        (name, inhalt, beschreibungen[name]) for name, inhalt in inhalte
    ]


def als_zip(profil_id: int, von: date, bis: date) -> tuple[bytes, list[tuple[str, str, str]]]:
    """Liefert das ZIP und die enthaltenen Dateien mit ihrer Beschreibung."""
    inhalte = dateien(profil_id, von, bis)
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as archiv:
        for name, inhalt, _ in inhalte:
            archiv.writestr(name, inhalt.encode(KODIERUNG))
    return puffer.getvalue(), inhalte
