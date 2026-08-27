"""Seite Aktivität: Tagesstruktur, Sporteinheiten und Tagesbedarf.

Der Tag wird vollständig in vier Blöcke aufgeteilt: Schlaf, Arbeit nach
Haltung, Sport und die berechnete Restzeit. Zusammen ergeben sie immer
1440 Minuten. Die MET-Werte kommen aus met_grundwert und sportart, hier
stehen keine.

Der Tagesbedarf wird bei jeder Anzeige frisch gerechnet und dabei in
tagesbedarf festgehalten, damit der gespeicherte Wert nicht veraltet.
"""
from __future__ import annotations

from datetime import date

import streamlit as st

from src import berechnung, datenbank

SPORT_KATEGORIE_ANZEIGE = {
    "joggen": "Joggen",
    "fahrrad": "Fahrrad",
    "kraftsport": "Kraftsport",
}


def _kcal(wert: float) -> str:
    return f"{wert:.0f} kcal"


def _dauer(minuten: int) -> str:
    stunden, rest = divmod(abs(int(minuten)), 60)
    vorzeichen = "-" if minuten < 0 else ""
    return f"{vorzeichen}{stunden} h {rest:02d} min"


# --------------------------------------------------------------------------- #
# Schlaf, Tagestyp und Arbeitszeiten
# --------------------------------------------------------------------------- #
def _tagesstruktur(profil_id: int, datum: date, met_werte: dict) -> None:
    st.subheader("Tagesstruktur")

    vorhanden = datenbank.tag_aktivitaet(profil_id, datum)
    tag = datum.isoformat()  # Teil der Widget-Schlüssel: bei Datumswechsel
    # werden die Felder mit den gespeicherten Werten neu aufgebaut.

    schlaf = st.number_input(
        "Schlaf (Minuten)",
        min_value=0,
        max_value=berechnung.MINUTEN_JE_TAG,
        value=int(vorhanden["min_schlaf"]) if vorhanden else 480,
        step=15,
        key=f"ak_min_schlaf_{tag}",
        help=f"MET {met_werte['schlaf']['met']:g} aus met_grundwert.",
    )

    typen = list(berechnung.TAGESTYPEN)
    gespeicherter_typ = vorhanden["tagestyp"] if vorhanden else None
    tagestyp = st.radio(
        "Tagestyp",
        typen,
        index=typen.index(gespeicherter_typ) if gespeicherter_typ in typen else 0,
        format_func=lambda wert: berechnung.TAGESTYP_ANZEIGE[wert],
        horizontal=True,
        key=f"ak_tagestyp_{tag}",
    )

    vorlage = berechnung.TAGESTYPEN[tagestyp]
    st.caption(
        "Die Vorlage belegt die Arbeitszeiten vor: "
        + ", ".join(
            f"{met_werte[schluessel]['name']} {vorlage[feld]} min"
            for feld, schluessel in berechnung.ERFASSTE_BLOECKE.items()
            if feld != "min_schlaf"
        )
        + ". Einzeln änderbar."
    )

    # Der Vorlagenwert gilt, solange der Tagestyp gewechselt wird; danach zählt,
    # was in den Feldern steht. Deshalb steckt der Tagestyp im Widget-Schlüssel.
    arbeit = {}
    spalten = st.columns(3)
    felder = [feld for feld in berechnung.ERFASSTE_BLOECKE if feld != "min_schlaf"]
    for spalte, feld in zip(spalten, felder):
        schluessel = berechnung.ERFASSTE_BLOECKE[feld]
        if vorhanden and gespeicherter_typ == tagestyp:
            startwert = int(vorhanden[feld])
        else:
            startwert = vorlage[feld]
        arbeit[feld] = spalte.number_input(
            f"{met_werte[schluessel]['name']} (Minuten)",
            min_value=0,
            max_value=berechnung.MINUTEN_JE_TAG,
            value=startwert,
            step=15,
            key=f"ak_{feld}_{tag}_{tagestyp}",
            help=f"MET {met_werte[schluessel]['met']:g}",
        )

    knopf1, knopf2 = st.columns(2)
    if knopf1.button("Tag speichern", type="primary"):
        try:
            datenbank.tag_aktivitaet_speichern(
                profil_id,
                datum,
                min_schlaf=schlaf,
                min_sitzend=arbeit["min_sitzend"],
                min_stehend=arbeit["min_stehend"],
                min_veranstaltung=arbeit["min_veranstaltung"],
                tagestyp=tagestyp,
            )
        except datenbank.DatenFehler as fehler:
            st.error(str(fehler))
            return
        st.rerun()

    if vorhanden and knopf2.button("Eintrag löschen"):
        datenbank.tag_aktivitaet_loeschen(profil_id, datum)
        st.rerun()

    if vorhanden is None:
        st.info("Für diesen Tag ist noch nichts gespeichert.")
    elif gespeicherter_typ and (
        any(int(vorhanden[feld]) != berechnung.TAGESTYPEN[gespeicherter_typ][feld] for feld in felder)
    ):
        st.caption(
            "Gespeichert als Tagestyp "
            f"{berechnung.TAGESTYP_ANZEIGE[gespeicherter_typ]} mit angepassten Minuten."
        )


# --------------------------------------------------------------------------- #
# Sporteinheiten, Auswahl in zwei Schritten
# --------------------------------------------------------------------------- #
def _sport(profil_id: int, datum: date) -> None:
    st.subheader("Sporteinheiten")

    kategorien = datenbank.sportkategorien()
    if not kategorien:
        st.warning(
            "Es sind keine Sportarten hinterlegt. Bitte zuerst "
            "`python import_sportarten.py` ausführen."
        )
    else:
        spalte1, spalte2, spalte3 = st.columns([1.2, 2, 1])
        kategorie = spalte1.selectbox(
            "Kategorie",
            kategorien,
            format_func=lambda wert: SPORT_KATEGORIE_ANZEIGE.get(wert, wert.capitalize()),
            key="sp_kategorie",
        )
        auswahl = datenbank.sportarten(kategorie)
        beschriftung = {
            zeile["sportart_id"]: f"{zeile['name']} — MET {zeile['met_wert']:g}"
            for zeile in auswahl
        }
        sportart_id = spalte2.selectbox(
            "Intensität",
            list(beschriftung),
            format_func=lambda kennung: beschriftung[kennung],
            key=f"sp_sportart_{kategorie}",
        )
        dauer_min = spalte3.number_input(
            "Dauer (Minuten)", min_value=1, max_value=berechnung.MINUTEN_JE_TAG,
            value=45, step=5, key="sp_dauer",
        )
        if st.button("Sporteinheit hinzufügen"):
            try:
                datenbank.sporteinheit_hinzufuegen(
                    profil_id, datum, int(sportart_id), int(dauer_min)
                )
            except datenbank.DatenFehler as fehler:
                st.error(str(fehler))
                return
            st.rerun()

    einheiten = datenbank.sporteinheiten(profil_id, datum)
    if not einheiten:
        st.caption("Für diesen Tag ist kein Sport erfasst.")
        return

    for einheit in einheiten:
        zeile = st.columns([3.2, 1.2, 1.2, 0.7])
        zeile[0].write(einheit["name"])
        zeile[1].write(f"{einheit['dauer_min']} min")
        zeile[2].write(f"MET {einheit['met_wert']:g}")
        if zeile[3].button("✕", key=f"sp_loeschen_{einheit['einheit_id']}", help="Einheit entfernen"):
            datenbank.sporteinheit_loeschen(einheit["einheit_id"])
            st.rerun()


# --------------------------------------------------------------------------- #
# Tagesbedarf
# --------------------------------------------------------------------------- #
def _aufschluesselung(bloecke: list[dict], met_werte: dict) -> None:
    """Zeigt alle Blöcke mit Minuten und kcal. Die Summe ist immer 1440 Minuten."""
    kopf = st.columns([2.6, 1.0, 1.4, 1.2])
    for spalte, text in zip(kopf, ("Block", "MET", "Dauer", "kcal")):
        spalte.caption(text)

    for block in bloecke:
        name = (
            met_werte[block["schluessel"]]["name"]
            if block["schluessel"] in met_werte
            else block["schluessel"]
        )
        zeile = st.columns([2.6, 1.0, 1.4, 1.2])
        zeile[0].write(name if block["art"] != "sport" else f"Sport: {name}")
        zeile[1].write(f"{block['met']:g}")
        zeile[2].write(f"{block['minuten']} min ({_dauer(block['minuten'])})")
        zeile[3].write(f"{block['kcal']:.1f}")

    summe = st.columns([2.6, 1.0, 1.4, 1.2])
    summe[0].write("**Summe**")
    summe[1].write("")
    summe[2].write(f"**{sum(block['minuten'] for block in bloecke)} min**")
    summe[3].write(f"**{sum(block['kcal'] for block in bloecke):.1f}**")


def _bedarf(profil_id: int, datum: date, met_werte: dict) -> None:
    st.subheader("Tagesbedarf")

    ergebnis = datenbank.tagesbedarf(profil_id, datum)
    status = ergebnis["status"]

    if status == "kind":
        st.info("Für Kinderprofile wird kein Tagesbedarf berechnet.")
        return
    if status == "met_fehlt":
        st.warning(
            "Es fehlen MET-Grundwerte: "
            + ", ".join(ergebnis["fehlende_met"])
            + ". Bitte `python import_met_grundwerte.py` ausführen."
        )
        return
    if status == "keine_aktivitaet":
        st.info(
            "Ohne Eintrag zur Tagesstruktur wird für diesen Tag kein Bedarf ausgegeben. "
            "Auch nicht ersatzweise der Grundumsatz."
        )
        return
    if status == "kein_gewicht":
        st.info("Für diesen Tag ist kein Gewicht bekannt, deshalb kein Bedarf.")
        return
    if status == "restzeit_negativ":
        fehl = -ergebnis["restzeit_min"]
        st.error(
            f"Die erfassten Zeiten ergeben zusammen mehr als 24 Stunden "
            f"({berechnung.MINUTEN_JE_TAG + fehl} von {berechnung.MINUTEN_JE_TAG} Minuten, "
            f"also {_dauer(fehl)} zu viel). Deshalb wird kein Bedarf ausgegeben."
        )
        _aufschluesselung(ergebnis["bloecke"], met_werte)
        return

    zeile = ergebnis["zeile"]
    spalten = st.columns(4)
    spalten[0].metric("Grundumsatz", _kcal(zeile["grundumsatz_kcal"]))
    spalten[1].metric("Aktivität", _kcal(zeile["aktivitaet_kcal"]))
    spalten[2].metric("Sport", _kcal(zeile["sport_kcal"]))
    spalten[3].metric("Bedarf", _kcal(zeile["bedarf_kcal"]))
    st.caption(
        f"Gerechnet mit {zeile['gewicht_kg_verwendet']:.1f} kg "
        f"(zuletzt bekanntes Gewicht bis zum {datum.strftime('%d.%m.%Y')}), "
        f"Stand {zeile['berechnet_am'].replace('T', ' ')}. "
        "Aktivität umfasst Schlaf, Arbeit und Restzeit."
    )

    eintrag = datenbank.profil(profil_id)
    rate = eintrag["aenderung_kg_woche"] if eintrag is not None else None
    if rate:
        ziel = berechnung.kalorienziel_kcal(zeile["bedarf_kcal"], rate)
        st.metric(
            "Kalorienziel",
            _kcal(ziel),
            delta=f"{rate * berechnung.KCAL_JE_KG / 7:+.0f} kcal gegenüber dem Bedarf",
            delta_color="off",
        )
        # Der Wert wird nicht begrenzt und nicht verändert, nur gekennzeichnet.
        if ziel < zeile["grundumsatz_kcal"]:
            st.warning(
                f"Dieses Kalorienziel liegt unter dem Grundumsatz von "
                f"{_kcal(zeile['grundumsatz_kcal'])}."
            )

    with st.expander("Aufschlüsselung des Tages", expanded=False):
        st.caption("(MET − 1) × Gewicht in kg × Dauer in Stunden, je Block.")
        _aufschluesselung(ergebnis["bloecke"], met_werte)
        st.caption(
            f"Restzeit ist berechnet: {berechnung.MINUTEN_JE_TAG} minus Schlaf, "
            "Arbeit und Sport. Sie wird nicht erfasst."
        )


# --------------------------------------------------------------------------- #
# Seite
# --------------------------------------------------------------------------- #
def seite() -> None:
    st.title("Aktivität")

    profil_id = st.session_state.get("profil_id")
    if profil_id is None:
        st.info("Lege zuerst ein Profil an. Aktivität hängt immer an einem Profil.")
        return

    met_werte = datenbank.met_grundwerte()
    fehlend = [
        schluessel
        for schluessel in (*berechnung.ERFASSTE_BLOECKE.values(), berechnung.REST_SCHLUESSEL)
        if schluessel not in met_werte
    ]
    if fehlend:
        st.error(
            "Die MET-Grundwerte fehlen (" + ", ".join(fehlend) + "). "
            "Bitte `python import_met_grundwerte.py` ausführen."
        )
        return

    datum = st.date_input("Datum", value=date.today(), format="DD.MM.YYYY", key="ak_datum")

    _tagesstruktur(profil_id, datum, met_werte)
    st.divider()
    _sport(profil_id, datum)
    st.divider()
    _bedarf(profil_id, datum, met_werte)
