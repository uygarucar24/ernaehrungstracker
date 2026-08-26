"""Seite Profilverwaltung: Profil anlegen und Übersicht des aktiven Profils."""
from __future__ import annotations

from datetime import date

import streamlit as st

from src import datenbank

GESCHLECHT_ANZEIGE = {"m": "männlich", "w": "weiblich"}
TYP_ANZEIGE = {"erwachsen": "Erwachsen", "kind": "Kind"}
ZIEL_ANZEIGE = {"abnehmen": "Abnehmen", "zunehmen": "Zunehmen", "halten": "Gewicht halten"}


# --------------------------------------------------------------------------- #
# Hilfsfunktionen
# --------------------------------------------------------------------------- #
def alter_in_jahren(geburtsdatum: date, stichtag: date | None = None) -> int:
    """Alter wird berechnet, nicht gespeichert."""
    stichtag = stichtag or date.today()
    vorbei = (stichtag.month, stichtag.day) < (geburtsdatum.month, geburtsdatum.day)
    return stichtag.year - geburtsdatum.year - int(vorbei)


def als_datum(wert: str) -> date:
    return date.fromisoformat(str(wert))


# --------------------------------------------------------------------------- #
# Übersicht des aktiven Profils
# --------------------------------------------------------------------------- #
def zeige_uebersicht(profil_id: int) -> None:
    # Erreichtes Zielgewicht stellt den Modus auf halten, bevor gelesen wird.
    umgestellt = datenbank.ziel_status_aktualisieren(profil_id)

    eintrag = datenbank.profil(profil_id)
    if eintrag is None:
        st.warning("Das gewählte Profil ist nicht mehr vorhanden.")
        return

    geburtsdatum = als_datum(eintrag["geburtsdatum"])
    st.header(eintrag["name"])
    st.caption(f"Profiltyp: {TYP_ANZEIGE.get(eintrag['typ'], eintrag['typ'])}")

    gewicht = datenbank.letztes_gewicht(profil_id)

    spalte1, spalte2, spalte3 = st.columns(3)
    spalte1.metric("Alter", f"{alter_in_jahren(geburtsdatum)} Jahre")
    spalte2.metric("Größe", f"{eintrag['groesse_cm']:.0f} cm")
    if gewicht is None:
        spalte3.metric("Gewicht", "kein Eintrag")
    else:
        spalte3.metric(
            "Gewicht",
            f"{gewicht['gewicht_kg']:.1f} kg",
            help=f"Stand {als_datum(gewicht['datum']).strftime('%d.%m.%Y')}",
        )

    st.write(f"**Geburtsdatum:** {geburtsdatum.strftime('%d.%m.%Y')}")
    st.write(
        "**Geschlecht:** "
        + GESCHLECHT_ANZEIGE.get(eintrag["geschlecht"], eintrag["geschlecht"])
    )

    # Ausdrückliche Prüfung des Typs: Ziel und Änderungsrate gibt es nur bei
    # Erwachsenenprofilen, bei Kinderprofilen wird dazu nichts angezeigt.
    if eintrag["typ"] == "erwachsen":
        st.subheader("Ziel")
        if umgestellt:
            st.info("Zielgewicht erreicht. Das Ziel steht jetzt auf Gewicht halten.")

        modus = eintrag["ziel_modus"] or "halten"
        ziel = eintrag["zielgewicht_kg"]
        rate = eintrag["aenderung_kg_woche"]

        if modus == "halten":
            st.metric("Richtung", ZIEL_ANZEIGE["halten"])
        else:
            ziel1, ziel2, ziel3 = st.columns(3)
            ziel1.metric("Richtung", ZIEL_ANZEIGE[modus])
            ziel2.metric("Zielgewicht", f"{ziel:.1f} kg")
            ziel3.metric("Änderung je Woche", f"{rate:+.2f} kg")

    st.subheader("Unverträglichkeiten")
    eintraege = datenbank.unvertraeglichkeiten(profil_id)
    if not eintraege:
        st.write("Keine hinterlegt.")
    for zeile in eintraege:
        st.write(
            f"- {zeile['bezeichnung'].capitalize()} "
            f"(Prüfweg: {zeile['pruefweg']}, Nährstoff-ID: {zeile['naehrstoff_id']})"
        )


# --------------------------------------------------------------------------- #
# Eingabemaske für ein neues Profil
# Der Profiltyp steht bewusst außerhalb eines st.form, damit die Felder für
# Zielgewicht und Tempo bei einem Kinderprofil gar nicht erst aufgebaut werden.
# --------------------------------------------------------------------------- #
def zeige_neues_profil() -> None:
    st.header("Neues Profil")

    typ = st.radio(
        "Profiltyp",
        ["erwachsen", "kind"],
        format_func=lambda wert: TYP_ANZEIGE[wert],
        horizontal=True,
        key="neu_typ",
    )

    name = st.text_input("Name", key="neu_name")

    spalte1, spalte2 = st.columns(2)
    geburtsdatum = spalte1.date_input(
        "Geburtsdatum",
        value=date(1990, 1, 1),
        min_value=date(1900, 1, 1),
        max_value=date.today(),
        format="DD.MM.YYYY",
        key="neu_geburtsdatum",
    )
    geschlecht = spalte2.radio(
        "Geschlecht",
        ["m", "w"],
        format_func=lambda wert: GESCHLECHT_ANZEIGE[wert],
        horizontal=True,
        key="neu_geschlecht",
    )

    spalte3, spalte4 = st.columns(2)
    groesse_cm = spalte3.number_input(
        "Größe in cm",
        min_value=30.0,
        max_value=250.0,
        value=175.0,
        step=0.5,
        key="neu_groesse",
    )
    gewicht_kg = spalte4.number_input(
        "Aktuelles Gewicht in kg",
        min_value=1.0,
        max_value=400.0,
        value=75.0,
        step=0.1,
        key="neu_gewicht",
        help="Wird als erster Eintrag in der Gewichtstabelle gespeichert, nicht im Profil.",
    )

    ziel_modus: str | None = None
    zielgewicht_kg: float | None = None
    tempo_kg_woche: float | None = None
    if typ == "erwachsen":
        st.subheader("Ziel")
        ziel_modus = st.radio(
            "Was ist das Ziel?",
            list(datenbank.ZIEL_MODI),
            format_func=lambda wert: ZIEL_ANZEIGE[wert],
            horizontal=True,
            key="neu_ziel_modus",
        )
        # Bei halten bleiben Zielgewicht und Tempo leer, die Felder erscheinen
        # gar nicht erst. Das Vorzeichen der Rate setzt der Modus.
        if ziel_modus != "halten":
            spalte5, spalte6 = st.columns(2)
            zielgewicht_kg = spalte5.number_input(
                "Zielgewicht in kg",
                min_value=1.0,
                max_value=400.0,
                value=float(gewicht_kg),
                step=0.1,
                key="neu_zielgewicht",
            )
            tempo_kg_woche = spalte6.number_input(
                "Tempo in kg pro Woche",
                min_value=0.05,
                max_value=2.0,
                value=0.5,
                step=0.05,
                key="neu_tempo",
                help="Ohne Vorzeichen. Die Richtung kommt aus dem Ziel.",
            )

    st.subheader("Unverträglichkeiten")
    laktose = st.checkbox("Laktoseintoleranz", key="neu_laktose")

    if st.button("Profil anlegen", type="primary"):
        if not name.strip():
            st.error("Bitte einen Namen eingeben.")
            return
        try:
            neue_id = datenbank.profil_anlegen(
                name=name.strip(),
                geburtsdatum=geburtsdatum,
                geschlecht=geschlecht,
                groesse_cm=float(groesse_cm),
                typ=typ,
                gewicht_kg=float(gewicht_kg),
                ziel_modus=ziel_modus,
                zielgewicht_kg=zielgewicht_kg,
                tempo_kg_woche=tempo_kg_woche,
                laktoseintoleranz=laktose,
            )
        except datenbank.DatenFehler as fehler:
            st.error(str(fehler))
            return

        st.session_state["profil_id"] = neue_id
        st.session_state["ansicht"] = "uebersicht"
        st.rerun()


# --------------------------------------------------------------------------- #
# Seite
# --------------------------------------------------------------------------- #
def seite() -> None:
    st.title("Profilverwaltung")

    vorhandene = datenbank.profile()
    if not vorhandene:
        st.session_state["ansicht"] = "neu"
    st.session_state.setdefault("ansicht", "uebersicht")

    if st.session_state["ansicht"] == "neu":
        if vorhandene and st.button("Zurück zur Übersicht"):
            st.session_state["ansicht"] = "uebersicht"
            st.rerun()
        zeige_neues_profil()
    else:
        if st.button("Neues Profil anlegen"):
            st.session_state["ansicht"] = "neu"
            st.rerun()
        zeige_uebersicht(st.session_state["profil_id"])
