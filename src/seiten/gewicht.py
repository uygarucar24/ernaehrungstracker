"""Seite Gewicht: Erfassung je Datum und Verlauf als Diagramm.

Gezeichnet werden nur Tage mit Eintrag. Tage ohne Eintrag werden übersprungen,
beide Linien laufen durch. Die Punkte zeigen, an welchen Tagen tatsächlich
gemessen wurde.
"""
from __future__ import annotations

from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from src import datenbank

# Der gleitende Durchschnitt läuft über ein Kalenderfenster: der Tag selbst und
# die sechs Tage davor. Wie viele Werte darin liegen, ist offen, es können eins
# bis sieben sein.
FENSTER_TAGE = 7

ZEITRAEUME = {
    "vier_wochen": ("Letzte 4 Wochen", 28),
    "zwoelf_monate": ("Letzte 12 Monate", 365),
    "gesamt": ("Gesamter Zeitraum", None),
}

FARBE_TAG = "#a8c8e8"
FARBE_SCHNITT = "#0b4f9e"


# --------------------------------------------------------------------------- #
# Erfassung
# --------------------------------------------------------------------------- #
def _erfassung(profil_id: int) -> None:
    st.subheader("Gewicht erfassen")

    spalte1, spalte2, spalte3 = st.columns([1.2, 1, 1])
    datum = spalte1.date_input(
        "Datum", value=date.today(), max_value=date.today(), format="DD.MM.YYYY", key="gw_datum"
    )
    vorhanden = datenbank.gewicht_am(profil_id, datum)
    letztes = datenbank.letztes_gewicht(profil_id)
    startwert = (
        float(vorhanden["gewicht_kg"])
        if vorhanden
        else float(letztes["gewicht_kg"]) if letztes else 75.0
    )
    gewicht_kg = spalte2.number_input(
        "Gewicht in kg",
        min_value=1.0,
        max_value=400.0,
        value=startwert,
        step=0.1,
        key=f"gw_wert_{datum.isoformat()}",
    )
    spalte3.write("")
    if spalte3.button("Speichern", type="primary", width="stretch"):
        try:
            datenbank.gewicht_speichern(profil_id, datum, float(gewicht_kg))
        except datenbank.DatenFehler as fehler:
            st.error(str(fehler))
            return
        st.rerun()

    if vorhanden:
        st.caption(
            f"Für den {datum.strftime('%d.%m.%Y')} sind bereits "
            f"{vorhanden['gewicht_kg']:.1f} kg erfasst. Speichern ersetzt den Wert."
        )


# --------------------------------------------------------------------------- #
# Verlauf
# --------------------------------------------------------------------------- #
def _tabelle(eintraege: list, von: date | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Liefert (Messwerte, Durchschnitt) als zwei getrennte Reihen.

    Messwerte enthält nur Tage mit Eintrag. Der Durchschnitt wird dagegen für
    jeden Kalendertag gerechnet, in dessen Fenster mindestens ein Messwert
    liegt, auch wenn an dem Tag selbst nicht gewogen wurde. Das Fenster ist der
    Tag selbst plus die sechs davor; ein älterer Wert fällt heraus.

    Der Durchschnitt endet spätestens heute, es wird nicht in die Zukunft
    gezeichnet.
    """
    roh = pd.DataFrame(
        {
            "datum": pd.to_datetime([zeile["datum"] for zeile in eintraege]),
            "gewicht": [float(zeile["gewicht_kg"]) for zeile in eintraege],
        }
    ).sort_values("datum")

    erster, letzter = roh["datum"].min(), roh["datum"].max()
    ende = min(pd.Timestamp(date.today()), letzter + pd.Timedelta(days=FENSTER_TAGE - 1))
    kalender = pd.date_range(start=erster, end=max(ende, letzter), freq="D")

    # Tage ohne Eintrag stehen als leere Werte im Kalender. rolling() mittelt
    # nur die vorhandenen Werte im Fenster, min_periods zählt ebenfalls nur sie.
    reihe = roh.set_index("datum")["gewicht"].reindex(kalender)
    schnitt = pd.DataFrame(
        {
            "datum": kalender,
            "schnitt": reihe.rolling(window=f"{FENSTER_TAGE}D", min_periods=1).mean().to_numpy(),
        }
    ).dropna(subset=["schnitt"])

    if von is not None:
        grenze = pd.Timestamp(von)
        roh = roh[roh["datum"] >= grenze]
        schnitt = schnitt[schnitt["datum"] >= grenze]

    return roh.reset_index(drop=True), schnitt.reset_index(drop=True)


def _diagramm(messwerte: pd.DataFrame, schnittwerte: pd.DataFrame) -> alt.LayerChart:
    x = alt.X("datum:T", title="Datum", axis=alt.Axis(format="%d.%m.%y"))
    skala = alt.Scale(zero=False, nice=True)

    tageswerte = (
        alt.Chart(messwerte)
        .mark_line(
            color=FARBE_TAG,
            strokeWidth=1.5,
            opacity=0.9,
            point=alt.OverlayMarkDef(color=FARBE_TAG, size=28),
        )
        .encode(
            x=x,
            y=alt.Y("gewicht:Q", title="Gewicht in kg", scale=skala),
            tooltip=[
                alt.Tooltip("datum:T", title="Datum", format="%d.%m.%Y"),
                alt.Tooltip("gewicht:Q", title="Gewicht", format=".1f"),
            ],
        )
    )
    # Bewusst ohne Punkte: eine berechnete Kurve, keine Messreihe.
    schnitt = (
        alt.Chart(schnittwerte)
        .mark_line(color=FARBE_SCHNITT, strokeWidth=3)
        .encode(
            x=x,
            y=alt.Y("schnitt:Q", title="Gewicht in kg", scale=skala),
            tooltip=[
                alt.Tooltip("datum:T", title="Datum", format="%d.%m.%Y"),
                alt.Tooltip("schnitt:Q", title="7-Tage-Schnitt", format=".2f"),
            ],
        )
    )
    return alt.layer(tageswerte, schnitt).resolve_scale(y="shared").properties(height=340)


def _verlauf(profil_id: int) -> None:
    st.subheader("Verlauf")

    schluessel = st.radio(
        "Zeitraum",
        list(ZEITRAEUME),
        format_func=lambda wert: ZEITRAEUME[wert][0],
        horizontal=True,
        key="gw_zeitraum",
    )
    tage = ZEITRAEUME[schluessel][1]
    von = date.today() - timedelta(days=tage) if tage else None

    # Sechs Tage Vorlauf, damit der Durchschnitt am Anfang des Zeitraums nicht
    # abgeschnitten ist. Gezeichnet und gezählt wird trotzdem erst ab von.
    vorlauf = von - timedelta(days=FENSTER_TAGE - 1) if von else None
    eintraege = datenbank.gewichtsverlauf(profil_id, vorlauf)
    im_zeitraum = [
        zeile
        for zeile in eintraege
        if von is None or date.fromisoformat(str(zeile["datum"])) >= von
    ]
    if not im_zeitraum:
        st.info("Für diesen Zeitraum ist noch kein Gewicht erfasst.")
        return

    messwerte, schnittwerte = _tabelle(eintraege, von)
    st.altair_chart(_diagramm(messwerte, schnittwerte), width="stretch")

    anzahl = len(im_zeitraum)
    if tage:
        zeitraum_tage = tage
    else:
        erster = date.fromisoformat(str(eintraege[0]["datum"]))
        zeitraum_tage = (date.today() - erster).days + 1

    st.caption(
        "Die Darstellung beruht auf "
        + ("einem erfassten Tag" if anzahl == 1 else f"{anzahl} erfassten Tagen")
        + f". Der gewählte Zeitraum umfasst {zeitraum_tage} Tage."
    )


# --------------------------------------------------------------------------- #
# Seite
# --------------------------------------------------------------------------- #
def seite() -> None:
    st.title("Gewicht")

    profil_id = st.session_state.get("profil_id")
    if profil_id is None:
        st.info("Lege zuerst ein Profil an. Gewicht hängt immer an einem Profil.")
        return

    _erfassung(profil_id)
    st.divider()
    _verlauf(profil_id)
