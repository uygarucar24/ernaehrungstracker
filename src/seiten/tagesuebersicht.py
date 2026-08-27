"""Seite Tagesübersicht: Bedarf, Kalorienziel und Aufnahme an einem Tag.

Maßgeblich für die Differenz ist das Kalorienziel, nicht der Bedarf. Fehlt der
Eintrag in tag_aktivitaet, gibt es keinen Bedarf und damit keine Bilanz; es wird
nicht ersatzweise gegen den Grundumsatz oder einen Durchschnitt gerechnet.
"""
from __future__ import annotations

from datetime import date

import streamlit as st

from src import berechnung, datenbank
from src.seiten.mahlzeiten import ABSCHNITT_ANZEIGE, ANZEIGE_NAEHRSTOFFE, CODES

ENERGIE = "ENERCC"
MAKROS = tuple(code for code, _ in ANZEIGE_NAEHRSTOFFE if code != ENERGIE)


def _kcal(wert: float) -> str:
    return f"{wert:.0f} kcal"


def _energie(summe: float, abdeckung: int) -> str:
    """Ohne einen einzigen bekannten Wert ist die Summe unbekannt, nicht 0."""
    return _kcal(summe) if abdeckung else "unbekannt"


# --------------------------------------------------------------------------- #
# Aufnahme aus den Mahlzeiten
# --------------------------------------------------------------------------- #
def _aufnahme(profil_id: int, datum: date) -> dict:
    """Sammelt alle Positionen des Tages und rechnet Summen je Mahlzeit und gesamt."""
    positionen = datenbank.mahlzeiten_am_tag(profil_id, datum)
    werte = datenbank.naehrwerte([zeile["lebensmittel_id"] for zeile in positionen], CODES)

    je_mahlzeit = {}
    for zeile in positionen:
        je_mahlzeit.setdefault(zeile["tagesabschnitt"], []).append(zeile)

    alle = [(zeile["lebensmittel_id"], zeile["menge_g"]) for zeile in positionen]
    summen, abdeckung = berechnung.naehrwertsummen(
        alle, werte, CODES, datenbank.BEZUGSMENGE_G
    )

    mahlzeiten = []
    for abschnitt in datenbank.TAGESABSCHNITTE:
        zeilen = je_mahlzeit.get(abschnitt)
        if not zeilen:
            continue
        m_summen, m_abdeckung = berechnung.naehrwertsummen(
            [(z["lebensmittel_id"], z["menge_g"]) for z in zeilen],
            werte,
            CODES,
            datenbank.BEZUGSMENGE_G,
        )
        mahlzeiten.append(
            {
                "abschnitt": abschnitt,
                "positionen": zeilen,
                "summen": m_summen,
                "abdeckung": m_abdeckung,
            }
        )

    return {
        "positionen": positionen,
        "mahlzeiten": mahlzeiten,
        "summen": summen,
        "abdeckung": abdeckung,
        "ohne_energie": len(positionen) - abdeckung[ENERGIE],
        # Ohne erfasste Position oder ohne einen einzigen Kalorienwert ist die
        # Aufnahme unbekannt. Unbekannt ist nicht null.
        "bekannt": abdeckung[ENERGIE] > 0,
    }


# --------------------------------------------------------------------------- #
# Bilanz
# --------------------------------------------------------------------------- #
def _bilanz(profil_id: int, datum: date, aufnahme: dict) -> None:
    st.subheader("Bilanz")

    ergebnis = datenbank.tagesbedarf(profil_id, datum)
    status = ergebnis["status"]

    if status == "keine_aktivitaet":
        st.info(
            "Für diesen Tag ist keine Aktivität erfasst. Ohne Aktivitätseintrag gibt es "
            "keinen Tagesbedarf und damit keine Bilanz. Es wird nicht ersatzweise gegen "
            "den Grundumsatz oder einen Durchschnittswert gerechnet."
        )
        return
    if status == "kein_gewicht":
        st.info("Für diesen Tag ist kein Gewicht bekannt, deshalb kein Bedarf und keine Bilanz.")
        return
    if status == "met_fehlt":
        st.warning(
            "Es fehlen MET-Grundwerte: "
            + ", ".join(ergebnis["fehlende_met"])
            + ". Bitte `python import_met_grundwerte.py` ausführen."
        )
        return
    if status == "restzeit_negativ":
        st.error(
            "Die erfassten Zeiten des Tages ergeben zusammen mehr als 24 Stunden. "
            "Solange das so ist, gibt es keinen Bedarf und keine Bilanz."
        )
        return
    if status != "ok":
        st.info("Für diesen Tag lässt sich kein Bedarf ermitteln, deshalb keine Bilanz.")
        return

    zeile = ergebnis["zeile"]
    bedarf = zeile["bedarf_kcal"]

    st.caption("Bedarf")
    spalten = st.columns(4)
    spalten[0].metric("Grundumsatz", _kcal(zeile["grundumsatz_kcal"]))
    spalten[1].metric("Aktivität", _kcal(zeile["aktivitaet_kcal"]))
    spalten[2].metric("Sport", _kcal(zeile["sport_kcal"]))
    spalten[3].metric("Bedarf", _kcal(bedarf))

    eintrag = datenbank.profil(profil_id)
    rate = eintrag["aenderung_kg_woche"] if eintrag is not None else None
    modus = eintrag["ziel_modus"] if eintrag is not None else None
    # Ohne Rate ist das Ziel der Bedarf; bei "halten" sind beide identisch.
    ziel = berechnung.kalorienziel_kcal(bedarf, rate) if rate else bedarf

    st.caption("Bilanz gegen das Kalorienziel")

    def _ziel_kennzahl(behaelter) -> None:
        if rate:
            behaelter.metric(
                "Kalorienziel",
                _kcal(ziel),
                delta=f"{rate * berechnung.KCAL_JE_KG / 7:+.0f} kcal gegenüber dem Bedarf",
                delta_color="off",
            )
        else:
            behaelter.metric(
                "Kalorienziel", _kcal(ziel), help="Ohne Änderungsrate gleich dem Bedarf."
            )

    # Unbekannte Aufnahme wird nicht wie eine Aufnahme von null behandelt:
    # ohne bekannten Kalorienwert gibt es keine Aufnahme und keine Differenz.
    if not aufnahme["bekannt"]:
        _ziel_kennzahl(st)
        if not aufnahme["positionen"]:
            st.info(
                "Für diesen Tag ist keine Mahlzeit erfasst. Ohne erfasste Position gibt es "
                "keine Aufnahme und damit keine Bilanz. Es wird nicht mit einer Aufnahme "
                "von 0 kcal gerechnet."
            )
        elif len(aufnahme["positionen"]) == 1:
            st.info(
                "Die einzige erfasste Position hat keinen Kalorienwert. Damit ist die "
                "Aufnahme unbekannt und es gibt keine Bilanz."
            )
        else:
            st.info(
                f"Keine der {len(aufnahme['positionen'])} erfassten Positionen hat einen "
                "Kalorienwert. Damit ist die Aufnahme unbekannt und es gibt keine Bilanz."
            )
        return

    aufgenommen = aufnahme["summen"][ENERGIE]
    differenz = ziel - aufgenommen

    spalten = st.columns(3)
    _ziel_kennzahl(spalten[0])
    spalten[1].metric("Aufnahme", _kcal(aufgenommen))
    spalten[2].metric("Differenz", f"{differenz:+.0f} kcal")

    if differenz > 0:
        st.success(f"Noch {differenz:.0f} kcal bis zum Kalorienziel verfügbar.")
    elif differenz < 0:
        st.warning(f"Das Kalorienziel ist um {abs(differenz):.0f} kcal überschritten.")
    else:
        st.info("Das Kalorienziel ist genau erreicht.")

    if modus == "halten":
        st.caption("Das Profil steht auf Gewicht halten, deshalb sind Ziel und Bedarf gleich.")
    if zeile["grundumsatz_kcal"] > ziel:
        st.caption(
            f"Hinweis: Das Kalorienziel liegt unter dem Grundumsatz von "
            f"{_kcal(zeile['grundumsatz_kcal'])}."
        )
    if aufnahme["ohne_energie"]:
        st.caption(
            f"Die Differenz beruht auf einer unvollständig erfassten Aufnahme: "
            f"{aufnahme['ohne_energie']} Position(en) ohne Kalorienwert."
        )


# --------------------------------------------------------------------------- #
# Mahlzeiten und Makronährstoffe
# --------------------------------------------------------------------------- #
def _mahlzeiten(aufnahme: dict) -> None:
    st.subheader("Mahlzeiten des Tages")

    if not aufnahme["positionen"]:
        st.info("Für diesen Tag ist keine Mahlzeit erfasst.")
        return

    kopf = st.columns([2.2, 1.4, 1.4, 2.0])
    for spalte, text in zip(kopf, ("Mahlzeit", "Positionen", "Energie", "davon ohne Wert")):
        spalte.caption(text)

    for mahlzeit in aufnahme["mahlzeiten"]:
        anzahl = len(mahlzeit["positionen"])
        ohne = anzahl - mahlzeit["abdeckung"][ENERGIE]
        zeile = st.columns([2.2, 1.4, 1.4, 2.0])
        zeile[0].write(ABSCHNITT_ANZEIGE[mahlzeit["abschnitt"]])
        zeile[1].write(f"{anzahl}")
        zeile[2].write(_energie(mahlzeit["summen"][ENERGIE], mahlzeit["abdeckung"][ENERGIE]))
        zeile[3].write("—" if ohne == 0 else f"{ohne}")

    gesamt = len(aufnahme["positionen"])
    summe = st.columns([2.2, 1.4, 1.4, 2.0])
    summe[0].write("**Tagessumme**")
    summe[1].write(f"**{gesamt}**")
    summe[2].write(f"**{_energie(aufnahme['summen'][ENERGIE], aufnahme['abdeckung'][ENERGIE])}**")
    summe[3].write("—" if aufnahme["ohne_energie"] == 0 else f"**{aufnahme['ohne_energie']}**")

    if aufnahme["ohne_energie"]:
        st.caption(
            f"{aufnahme['ohne_energie']} von {gesamt} Positionen haben keinen Kalorienwert. "
            "Die Tagessumme beruht auf den übrigen und ist damit unvollständig."
        )
    else:
        st.caption(f"Die Tagessumme beruht auf allen {gesamt} Positionen.")


def _makros(aufnahme: dict) -> None:
    st.subheader("Makronährstoffe des Tages")

    if not aufnahme["positionen"]:
        st.write("Keine Angaben, für diesen Tag ist keine Mahlzeit erfasst.")
        return

    stammdaten = datenbank.naehrstoffe(CODES)
    gesamt = len(aufnahme["positionen"])
    anzeige = dict(ANZEIGE_NAEHRSTOFFE)

    spalten = st.columns(len(MAKROS))
    for spalte, code in zip(spalten, MAKROS):
        einheit = stammdaten[code]["einheit"]
        # Wie in der Mahlzeitenansicht: ohne einen bekannten Wert unbekannt, keine 0.
        if aufnahme["abdeckung"][code] == 0:
            spalte.metric(anzeige[code], "unbekannt")
        else:
            spalte.metric(anzeige[code], f"{aufnahme['summen'][code]:.1f} {einheit}")
        spalte.caption(f"aus {aufnahme['abdeckung'][code]} von {gesamt}")


# --------------------------------------------------------------------------- #
# Seite
# --------------------------------------------------------------------------- #
def seite() -> None:
    st.title("Tagesübersicht")

    profil_id = st.session_state.get("profil_id")
    if profil_id is None:
        st.info("Lege zuerst ein Profil an. Die Übersicht hängt immer an einem Profil.")
        return

    datum = st.date_input("Datum", value=date.today(), format="DD.MM.YYYY", key="tu_datum")

    aufnahme = _aufnahme(profil_id, datum)

    # Ausdrückliche Prüfung des Profiltyps: im Kinderprofil gibt es keinen
    # Bedarf, kein Kalorienziel und keine Differenz, die Bilanz wird nicht
    # aufgebaut.
    eintrag = datenbank.profil(profil_id)
    ist_kind = eintrag is not None and eintrag["typ"] == "kind"

    if ist_kind:
        st.caption(
            "Kinderprofil: Es werden die Mahlzeiten und die Makronährstoffe gezeigt, "
            "kein Bedarf und keine Bilanz."
        )
    else:
        _bilanz(profil_id, datum, aufnahme)
        st.divider()

    _mahlzeiten(aufnahme)
    st.divider()
    _makros(aufnahme)
