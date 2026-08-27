"""Seite Gewicht: Erfassung je Datum und Verlauf als Diagramm.

Tage ohne Eintrag bleiben Lücken. Es wird nicht interpoliert und keine Linie
über eine Lücke gezogen: fehlende Tage stehen als leere Werte in den Daten,
und beide Linien brechen dort ab.
"""
from __future__ import annotations

from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from src import datenbank

# Der gleitende Durchschnitt läuft über sieben erfasste Werte und beginnt
# erst, wenn sieben vorliegen.
FENSTER = 7

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
def _tabelle(eintraege: list, von: date | None) -> pd.DataFrame:
    """Baut eine Zeile je Kalendertag; Tage ohne Eintrag bleiben leer.

    Der gleitende Durchschnitt wird über die erfassten Werte gerechnet und
    danach wieder auf ihre Tage gelegt. So steht an einem Tag ohne Eintrag
    auch kein Durchschnitt, und beide Linien brechen an der Lücke ab.
    """
    erfasst = pd.DataFrame(
        {
            "datum": pd.to_datetime([zeile["datum"] for zeile in eintraege]),
            "gewicht": [float(zeile["gewicht_kg"]) for zeile in eintraege],
        }
    ).sort_values("datum")
    erfasst["schnitt"] = (
        erfasst["gewicht"].rolling(window=FENSTER, min_periods=FENSTER).mean()
    )

    beginn = pd.Timestamp(von) if von else erfasst["datum"].min()
    alle_tage = pd.date_range(start=min(beginn, erfasst["datum"].min()),
                              end=max(erfasst["datum"].max(), pd.Timestamp(date.today())),
                              freq="D")
    return (
        erfasst.set_index("datum")
        .reindex(alle_tage)
        .rename_axis("datum")
        .reset_index()
    )


def _diagramm(daten: pd.DataFrame) -> alt.LayerChart:
    x = alt.X("datum:T", title="Datum", axis=alt.Axis(format="%d.%m.%y"))
    y = alt.Y(
        "gewicht:Q",
        title="Gewicht in kg",
        scale=alt.Scale(zero=False, nice=True),
    )

    tageswerte = (
        alt.Chart(daten)
        .mark_line(color=FARBE_TAG, strokeWidth=1.5, opacity=0.9,
                   point=alt.OverlayMarkDef(color=FARBE_TAG, size=28))
        .encode(
            x=x,
            y=y,
            tooltip=[
                alt.Tooltip("datum:T", title="Datum", format="%d.%m.%Y"),
                alt.Tooltip("gewicht:Q", title="Gewicht", format=".1f"),
            ],
        )
    )
    schnitt = (
        alt.Chart(daten)
        .mark_line(color=FARBE_SCHNITT, strokeWidth=3)
        .encode(
            x=x,
            y=alt.Y("schnitt:Q", title="Gewicht in kg", scale=alt.Scale(zero=False, nice=True)),
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

    eintraege = datenbank.gewichtsverlauf(profil_id, von)
    if not eintraege:
        st.info("Für diesen Zeitraum ist noch kein Gewicht erfasst.")
        return

    daten = _tabelle(eintraege, von)
    st.altair_chart(_diagramm(daten), width="stretch")

    mit_schnitt = int(daten["schnitt"].notna().sum())
    anzahl = len(eintraege)
    st.caption(
        "Die Darstellung beruht auf "
        + ("einem erfassten Tag" if anzahl == 1 else f"{anzahl} erfassten Tagen")
        + " im gewählten Zeitraum."
    )
    if mit_schnitt == 0:
        st.caption(
            f"Der gleitende Durchschnitt beginnt ab dem {FENSTER}. Wert; "
            f"bisher liegen {len(eintraege)} vor."
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
