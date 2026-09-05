"""Seite Tagesübersicht: Bedarf, Kalorienziel und Aufnahme an einem Tag.

Maßgeblich für die Differenz ist das Kalorienziel, nicht der Bedarf. Fehlt der
Eintrag in tag_aktivitaet, gibt es keinen Bedarf und damit keine Bilanz; es wird
nicht ersatzweise gegen den Grundumsatz oder einen Durchschnitt gerechnet.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

import streamlit as st

from src import berechnung, datenbank
from src.seiten.mahlzeiten import ABSCHNITT_ANZEIGE, ANZEIGE_NAEHRSTOFFE, CODES

ENERGIE = "ENERCC"
MAKROS = tuple(code for code, _ in ANZEIGE_NAEHRSTOFFE if code != ENERGIE)

# Fettlösliche Vitamine. Die übrigen sind wasserlöslich. Die Unterteilung steht
# hier und nicht in naehrstoff.gruppe, weil sie nur der Anzeige dient.
FETTLOESLICHE_VITAMINE = ("VITA", "VITAA", "VITD", "VITE", "VITK")

# Anteile am Energiegehalt werden vorerst nicht verglichen.
NICHT_VERGLEICHEN = ("prozent_energie",)

WOCHE_TAGE = 7


def _kcal(wert: float) -> str:
    return f"{wert:.0f} kcal"


def _energie(summe: float, abdeckung: float) -> str:
    """Ohne abgedeckte Menge ist die Summe unbekannt, nicht 0."""
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
    summen, abdeckung, gesamtmenge = berechnung.naehrwertsummen(
        alle, werte, CODES, datenbank.BEZUGSMENGE_G
    )

    mahlzeiten = []
    for abschnitt in datenbank.TAGESABSCHNITTE:
        zeilen = je_mahlzeit.get(abschnitt)
        if not zeilen:
            continue
        m_summen, m_abdeckung, m_menge = berechnung.naehrwertsummen(
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
                "menge_g": m_menge,
                # Zahl der Positionen ohne Kalorienwert. Sie steht neben der
                # Abdeckung, weil die Spalte ausdrücklich Positionen zählt.
                "ohne_energie": sum(
                    1
                    for z in zeilen
                    if werte.get((z["lebensmittel_id"], ENERGIE)) is None
                ),
            }
        )

    return {
        "positionen": positionen,
        "mahlzeiten": mahlzeiten,
        "summen": summen,
        "abdeckung": abdeckung,
        "menge_g": gesamtmenge,
        "ohne_energie": sum(
            1 for z in positionen if werte.get((z["lebensmittel_id"], ENERGIE)) is None
        ),
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
            + ". Bitte `python importe/import_met_grundwerte.py` ausführen."
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
        ohne = mahlzeit["ohne_energie"]
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
    gesamtmenge = aufnahme["menge_g"]
    anzeige = dict(ANZEIGE_NAEHRSTOFFE)

    spalten = st.columns(len(MAKROS))
    for spalte, code in zip(spalten, MAKROS):
        einheit = stammdaten[code]["einheit"]
        # Wie in der Mahlzeitenansicht: ohne einen bekannten Wert unbekannt, keine 0.
        if aufnahme["abdeckung"][code] == 0:
            spalte.metric(anzeige[code], "unbekannt")
        else:
            spalte.metric(anzeige[code], f"{aufnahme['summen'][code]:.1f} {einheit}")
        # Abdeckung als Mengenanteil: 200 g ohne Wert wiegen schwerer als 5 g.
        spalte.caption(berechnung.abdeckungstext(aufnahme["abdeckung"][code], gesamtmenge))


# --------------------------------------------------------------------------- #
# Vergleich mit den Referenzwerten
# --------------------------------------------------------------------------- #
def _zahl(wert: float | None, einheit: str) -> str:
    if wert is None:
        return "–"
    stellen = 0 if abs(wert) >= 100 else (1 if abs(wert) >= 10 else 2)
    return f"{wert:.{stellen}f} {einheit}"


def _referenztext(referenz: float | None, obergrenze: float | None, einheit: str) -> str:
    if referenz is not None and obergrenze is not None:
        return f"{_zahl(referenz, '')}bis {_zahl(obergrenze, einheit)}"
    if referenz is not None:
        return _zahl(referenz, einheit)
    if obergrenze is not None:
        return f"höchstens {_zahl(obergrenze, einheit)}"
    return "–"


def _vergleichszeilen(
    referenzen: list, werte: dict, gesamtmenge: float, gewicht_kg: float | None
):
    """Baut je Nährstoff eine Zeile aus Zufuhr, Referenzwert und Einstufung.

    werte: BLS-Code -> (Summe, abgedeckte Menge in Gramm).
    """
    zeilen = []
    for referenz in referenzen:
        if referenz["bezug"] in NICHT_VERGLEICHEN:
            continue
        summe, mit_wert = werte.get(referenz["bls_spalte"], (None, 0.0))
        sollwert = berechnung.referenz_je_gewicht(
            referenz["wert"], referenz["bezug"], gewicht_kg
        )
        obergrenze = berechnung.referenz_je_gewicht(
            referenz["obergrenze"], referenz["bezug"], gewicht_kg
        )
        zeilen.append(
            {
                "gruppe": referenz["gruppe"],
                "code": referenz["bls_spalte"],
                "name": referenz["name"],
                "einheit": referenz["einheit"],
                "zufuhr": summe,
                "abdeckung": mit_wert,
                "menge_g": gesamtmenge,
                "referenz": sollwert,
                "obergrenze": obergrenze,
                "art": referenz["art"],
                "bezug": referenz["bezug"],
                "einstufung": berechnung.einstufung(summe, sollwert, obergrenze, mit_wert),
            }
        )
    return zeilen


def _abschnitte(zeilen: list) -> list[tuple[str, list[tuple[str, list]]]]:
    """Teilt die Nährstoffe in aufklappbare Abschnitte mit Unterabschnitten.

    Energieliefernde Nährstoffe, Vitamine nach Löslichkeit, Mineralstoffe nach
    Mengen- und Spurenelementen.
    """
    vitamine = [z for z in zeilen if z["gruppe"] == "vitamin"]
    return [
        (
            "Energieliefernde Nährstoffe",
            [("", [z for z in zeilen if z["gruppe"] == "makronaehrstoff"])],
        ),
        (
            "Vitamine",
            [
                ("Fettlöslich", [z for z in vitamine if z["code"] in FETTLOESLICHE_VITAMINE]),
                ("Wasserlöslich", [z for z in vitamine if z["code"] not in FETTLOESLICHE_VITAMINE]),
            ],
        ),
        (
            "Mineralstoffe",
            [
                ("Mengenelemente", [z for z in zeilen if z["gruppe"] == "mineralstoff"]),
                ("Spurenelemente", [z for z in zeilen if z["gruppe"] == "spurenelement"]),
            ],
        ),
    ]


def _abschnittstitel(titel: str, zeilen: list) -> str:
    """Titel mit kurzer Übersicht, damit man ohne Aufklappen etwas sieht."""
    zaehler = Counter(z["einstufung"] for z in zeilen)
    teile = []
    for schluessel, wort in (
        (berechnung.UNTERHALB, "unterhalb"),
        (berechnung.OBERHALB, "oberhalb"),
        (berechnung.KEINE_AUSSAGE, "ohne Aussage"),
    ):
        if zaehler[schluessel]:
            teile.append(f"{zaehler[schluessel]} {wort}")
    if not teile:
        teile.append("alle im Bereich")
    return f"{titel} ({len(zeilen)}) — " + ", ".join(teile)


def _vergleichstabelle(zeilen: list) -> None:
    breiten = [2.6, 1.5, 1.7, 2.2, 1.5, 1.3]
    kopf = st.columns(breiten)
    for spalte, text in zip(
        kopf, ("Nährstoff", "Zufuhr", "Referenzwert", "Einstufung", "Art", "Abdeckung Menge")
    ):
        spalte.caption(text)
    for zeile in zeilen:
        spalten = st.columns(breiten)
        name = zeile["name"] + (" (je kg)" if zeile["bezug"] == "je_kg" else "")
        spalten[0].write(name)
        spalten[1].write(
            _zahl(zeile["zufuhr"], zeile["einheit"]) if zeile["abdeckung"] else "unbekannt"
        )
        spalten[2].write(_referenztext(zeile["referenz"], zeile["obergrenze"], zeile["einheit"]))
        spalten[3].write(berechnung.EINSTUFUNG_ANZEIGE[zeile["einstufung"]])
        spalten[4].write(zeile["art"] or "–")
        spalten[5].write(
            berechnung.abdeckungstext(zeile["abdeckung"], zeile["menge_g"], kurz=True)
        )


def _vergleich(
    profil_id: int, datum: date, eintrag, aufnahme: dict, referenzen: list, alter: int
) -> None:
    st.subheader("Nährstoffe im Vergleich mit den Referenzwerten")

    if not referenzen:
        st.info(
            f"Für die Altersgruppe dieses Profils ({alter} Jahre) liegen keine "
            "Referenzwerte vor. Es wird nicht auf die nächstgelegene Altersgruppe "
            "ausgewichen, deshalb entfällt der Vergleich."
        )
        return

    if not aufnahme["positionen"]:
        st.info("Für diesen Tag ist keine Mahlzeit erfasst, deshalb kein Vergleich.")
        return

    gewicht = datenbank.gewicht_bis(profil_id, datum)
    gewicht_kg = gewicht["gewicht_kg"] if gewicht else None

    codes = tuple(zeile["bls_spalte"] for zeile in referenzen)
    werte_roh = datenbank.naehrwerte(
        [p["lebensmittel_id"] for p in aufnahme["positionen"]], codes
    )
    summen, abdeckung, gesamtmenge = berechnung.naehrwertsummen(
        [(p["lebensmittel_id"], p["menge_g"]) for p in aufnahme["positionen"]],
        werte_roh,
        codes,
        datenbank.BEZUGSMENGE_G,
    )
    werte = {code: (summen[code], abdeckung[code]) for code in codes}
    zeilen = _vergleichszeilen(referenzen, werte, gesamtmenge, gewicht_kg)

    st.caption(
        f"Altersgruppe {alter} Jahre, {'männlich' if eintrag['geschlecht'] == 'm' else 'weiblich'}. "
        + (
            f"Werte je Kilogramm Körpergewicht sind mit {gewicht_kg:.1f} kg gerechnet."
            if gewicht_kg
            else "Für Werte je Kilogramm Körpergewicht fehlt das Gewicht."
        )
    )
    st.caption(
        f"Die Spalte Abdeckung Menge nennt den Anteil der erfassten Menge von "
        f"{gesamtmenge:.0f} g, für den ein Wert vorliegt — nicht den Anteil der "
        "Lebensmittel. Liegt für keine Position ein Wert vor, ist keine Aussage möglich."
    )

    for titel, unterabschnitte in _abschnitte(zeilen):
        gesamt = [z for teil in unterabschnitte for z in teil[1]]
        if not gesamt:
            continue
        with st.expander(_abschnittstitel(titel, gesamt)):
            for untertitel, teil in unterabschnitte:
                if not teil:
                    continue
                if untertitel:
                    st.markdown(f"**{untertitel}**")
                _vergleichstabelle(teil)

    st.caption(
        "Referenzwerte gelten für gesunde Personengruppen und sind so bemessen, dass sie "
        "den Bedarf nahezu aller Personen dieser Gruppe decken. Eine Unterschreitung an "
        "einzelnen Tagen erlaubt deshalb keine Aussage über den tatsächlichen "
        "Nährstoffstatus. Nährstoffe mit Bezug auf den Energieanteil sind nicht enthalten."
    )


def _wochenauswertung(profil_id: int, datum: date, referenzen: list) -> None:
    st.subheader(f"Letzte {WOCHE_TAGE} Tage")

    von = datum - timedelta(days=WOCHE_TAGE - 1)
    je_tag = datenbank.aufnahme_je_tag(profil_id, von, datum)
    if not je_tag:
        st.info(
            f"Zwischen dem {von.strftime('%d.%m.%Y')} und dem {datum.strftime('%d.%m.%Y')} "
            "ist keine Mahlzeit erfasst."
        )
        return

    gewicht = datenbank.gewicht_bis(profil_id, datum)
    gewicht_kg = gewicht["gewicht_kg"] if gewicht else None

    zusammen = []
    for referenz in referenzen:
        if referenz["bezug"] in NICHT_VERGLEICHEN:
            continue
        sollwert = berechnung.referenz_je_gewicht(
            referenz["wert"], referenz["bezug"], gewicht_kg
        )
        obergrenze = berechnung.referenz_je_gewicht(
            referenz["obergrenze"], referenz["bezug"], gewicht_kg
        )
        tage_mit_aussage = 0
        tage_unterhalb = 0
        for eintrag in je_tag.values():
            # Abdeckung als Menge in Gramm; ohne abgedeckte Menge keine Aussage.
            summe, menge_mit_wert, _ = eintrag["werte"].get(
                referenz["bls_spalte"], (None, 0.0, 0)
            )
            urteil = berechnung.einstufung(summe, sollwert, obergrenze, menge_mit_wert)
            if urteil == berechnung.KEINE_AUSSAGE:
                continue
            tage_mit_aussage += 1
            if urteil == berechnung.UNTERHALB:
                tage_unterhalb += 1
        if tage_mit_aussage:
            zusammen.append(
                {
                    "gruppe": referenz["gruppe"],
                    "code": referenz["bls_spalte"],
                    "name": referenz["name"],
                    "unterhalb": tage_unterhalb,
                    "mit_aussage": tage_mit_aussage,
                }
            )

    if not zusammen:
        st.caption("Für keinen Nährstoff liegen im Zeitraum auswertbare Tage vor.")
        return

    st.caption(
        f"Erfasste Tage im Zeitraum: {len(je_tag)}. Tage ohne erfasste Mahlzeit zählen "
        "nicht mit und gelten nicht als Unterschreitung."
    )
    breiten = [3.0, 2.6, 2.4]
    for titel, unterabschnitte in _abschnitte(zusammen):
        gesamt = [z for teil in unterabschnitte for z in teil[1]]
        if not gesamt:
            continue
        betroffen = sum(1 for z in gesamt if z["unterhalb"])
        beschriftung = (
            f"{titel} ({len(gesamt)}) — {betroffen} mit Tagen unterhalb"
            if betroffen
            else f"{titel} ({len(gesamt)}) — an keinem Tag unterhalb"
        )
        with st.expander(beschriftung):
            for untertitel, teil in unterabschnitte:
                if not teil:
                    continue
                if untertitel:
                    st.markdown(f"**{untertitel}**")
                kopf = st.columns(breiten)
                for spalte, text in zip(kopf, ("Nährstoff", "Tage unterhalb", "beruht auf")):
                    spalte.caption(text)
                for eintrag in teil:
                    zeile = st.columns(breiten)
                    zeile[0].write(eintrag["name"])
                    zeile[1].write(f"{eintrag['unterhalb']} von {eintrag['mit_aussage']}")
                    zeile[2].write(f"{eintrag['mit_aussage']} erfassten Tagen")


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
    st.divider()

    # Der Vergleich gilt für beide Profiltypen, sofern die Altersgruppe
    # hinterlegt ist. Kalorienbilanz und Zielwerte bleiben davon unberührt.
    if eintrag is not None:
        alter = berechnung.alter_in_jahren(
            date.fromisoformat(str(eintrag["geburtsdatum"])), datum
        )
        referenzen = datenbank.referenzwerte(eintrag["geschlecht"], alter)
        _vergleich(profil_id, datum, eintrag, aufnahme, referenzen, alter)
        # Die Wochenauswertung haengt nicht am gewaehlten Tag: sie ist auch dann
        # sinnvoll, wenn fuer diesen Tag nichts erfasst ist.
        if referenzen:
            st.divider()
            _wochenauswertung(profil_id, datum, referenzen)
