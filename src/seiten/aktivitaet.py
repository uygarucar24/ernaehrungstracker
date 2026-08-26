"""Seite Aktivität: Haltungsanteile, Sporteinheiten und Tagesbedarf.

Der Tagesbedarf wird bei jeder Anzeige frisch gerechnet und dabei in
tagesbedarf festgehalten, damit der gespeicherte Wert nicht veraltet.
"""
from __future__ import annotations

from datetime import date

import streamlit as st

from src import berechnung, datenbank


def _kcal(wert: float) -> str:
    return f"{wert:.0f} kcal"


# --------------------------------------------------------------------------- #
# Haltungsanteile
# --------------------------------------------------------------------------- #
def _haltung(profil_id: int, datum: date) -> None:
    st.subheader("Arbeitszeit nach Haltung")
    st.caption(
        "Die drei Anteile überschneiden sich nicht und ergeben zusammen die Arbeitszeit. "
        f"MET: sitzend {berechnung.HALTUNG_MET['min_sitzend']}, "
        f"stehend {berechnung.HALTUNG_MET['min_stehend']}, "
        f"Veranstaltung {berechnung.HALTUNG_MET['min_veranstaltung']}."
    )

    vorhanden = datenbank.tag_aktivitaet(profil_id, datum)
    tag = datum.isoformat()  # Teil der Widget-Schlüssel, damit ein Datumswechsel
    # die Felder neu mit den gespeicherten Werten aufbaut.

    spalten = st.columns(3)
    minuten = {}
    for spalte, feld in zip(spalten, berechnung.HALTUNG_MET):
        minuten[feld] = spalte.number_input(
            berechnung.HALTUNG_ANZEIGE[feld] + " (Minuten)",
            min_value=0,
            max_value=24 * 60,
            value=int(vorhanden[feld]) if vorhanden else 0,
            step=15,
            key=f"ak_{feld}_{tag}",
        )

    knopf1, knopf2 = st.columns([1, 1])
    if knopf1.button("Aktivität speichern", type="primary"):
        try:
            datenbank.tag_aktivitaet_speichern(
                profil_id,
                datum,
                minuten["min_sitzend"],
                minuten["min_stehend"],
                minuten["min_veranstaltung"],
            )
        except datenbank.DatenFehler as fehler:
            st.error(str(fehler))
            return
        st.rerun()

    if vorhanden and knopf2.button("Eintrag löschen"):
        datenbank.tag_aktivitaet_loeschen(profil_id, datum)
        st.rerun()

    if vorhanden is None:
        st.info("Für diesen Tag ist noch keine Aktivität erfasst.")


# --------------------------------------------------------------------------- #
# Sporteinheiten
# --------------------------------------------------------------------------- #
def _sport(profil_id: int, datum: date) -> None:
    st.subheader("Sporteinheiten")

    katalog = datenbank.sportarten()
    if not katalog:
        st.warning(
            "Es sind keine Sportarten hinterlegt. Bitte zuerst "
            "`python import_sportarten.py` ausführen."
        )
    else:
        beschriftung = {
            zeile["sportart_id"]: f"{zeile['name']} (MET {zeile['met_wert']:g})"
            for zeile in katalog
        }
        spalte1, spalte2 = st.columns([3, 1])
        sportart_id = spalte1.selectbox(
            "Sportart",
            list(beschriftung),
            format_func=lambda kennung: beschriftung[kennung],
            key="sp_sportart",
        )
        dauer_min = spalte2.number_input(
            "Dauer (Minuten)",
            min_value=1,
            max_value=24 * 60,
            value=45,
            step=5,
            key="sp_dauer",
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
def _bedarf(profil_id: int, datum: date) -> None:
    st.subheader("Tagesbedarf")

    eintrag = datenbank.profil(profil_id)
    # Der Profiltyp steuert: für Kinderprofile wird kein Bedarf gerechnet.
    if eintrag is not None and eintrag["typ"] != "erwachsen":
        st.info("Für Kinderprofile wird kein Tagesbedarf berechnet.")
        return

    if datenbank.tag_aktivitaet(profil_id, datum) is None:
        st.info(
            "Ohne Aktivitätseintrag wird für diesen Tag kein Bedarf ausgegeben. "
            "Auch nicht ersatzweise der Grundumsatz."
        )
        return

    bedarf = datenbank.tagesbedarf(profil_id, datum)
    if bedarf is None:
        st.info("Für diesen Tag ist kein Gewicht bekannt, deshalb kein Bedarf.")
        return

    spalten = st.columns(4)
    spalten[0].metric("Grundumsatz", _kcal(bedarf["grundumsatz_kcal"]))
    spalten[1].metric("Aktivität", _kcal(bedarf["aktivitaet_kcal"]))
    spalten[2].metric("Sport", _kcal(bedarf["sport_kcal"]))
    spalten[3].metric("Bedarf", _kcal(bedarf["bedarf_kcal"]))
    st.caption(
        f"Gerechnet mit {bedarf['gewicht_kg_verwendet']:.1f} kg "
        f"(zuletzt bekanntes Gewicht bis zum {datum.strftime('%d.%m.%Y')}), "
        f"Stand {bedarf['berechnet_am'].replace('T', ' ')}."
    )

    rate = eintrag["aenderung_kg_woche"] if eintrag is not None else None
    if rate:
        ziel = berechnung.kalorienziel_kcal(bedarf["bedarf_kcal"], rate)
        st.metric(
            "Kalorienziel",
            _kcal(ziel),
            delta=f"{rate * berechnung.KCAL_JE_KG / 7:+.0f} kcal gegenüber dem Bedarf",
            delta_color="off",
        )

    with st.expander("Rechenweg je Tätigkeit"):
        gewicht = bedarf["gewicht_kg_verwendet"]
        aktivitaet = datenbank.tag_aktivitaet(profil_id, datum)
        st.write("(MET − 1) × Gewicht in kg × Dauer in Stunden")
        for feld, met in berechnung.HALTUNG_MET.items():
            minuten = aktivitaet[feld]
            st.write(
                f"- {berechnung.HALTUNG_ANZEIGE[feld]}: ({met} − 1) × {gewicht:.1f} × "
                f"{minuten}/60 = **{berechnung.mehrverbrauch_kcal(met, gewicht, minuten):.1f} kcal**"
            )
        for einheit in datenbank.sporteinheiten(profil_id, datum):
            st.write(
                f"- {einheit['name']}: ({einheit['met_wert']:g} − 1) × {gewicht:.1f} × "
                f"{einheit['dauer_min']}/60 = "
                f"**{berechnung.mehrverbrauch_kcal(einheit['met_wert'], gewicht, einheit['dauer_min']):.1f} kcal**"
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

    datum = st.date_input("Datum", value=date.today(), format="DD.MM.YYYY", key="ak_datum")

    _haltung(profil_id, datum)
    st.divider()
    _sport(profil_id, datum)
    st.divider()
    _bedarf(profil_id, datum)
