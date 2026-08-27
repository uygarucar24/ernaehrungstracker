"""Ernährungs- und Bewegungstracker – lokale Streamlit-Anwendung.

Starten mit:  streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

from src import datenbank
from src.seiten import aktivitaet, gewicht, mahlzeiten, profil

st.set_page_config(
    page_title="Ernährungs- und Bewegungstracker",
    page_icon="🥗",
    layout="centered",
    initial_sidebar_state="expanded",
)

datenbank.schema_anlegen()


# --------------------------------------------------------------------------- #
# Seitenleiste: Profilwechsel
# Gilt für alle Seiten. Das gewählte Profil bleibt über st.session_state für
# die Sitzung aktiv.
# --------------------------------------------------------------------------- #
def profilwahl() -> None:
    st.sidebar.title("Profil")

    vorhandene = datenbank.profile()
    if not vorhandene:
        st.sidebar.info("Noch kein Profil angelegt.")
        st.session_state.pop("profil_id", None)
        return

    ids = [zeile["profil_id"] for zeile in vorhandene]
    namen = {zeile["profil_id"]: zeile["name"] for zeile in vorhandene}

    if st.session_state.get("profil_id") not in ids:
        st.session_state["profil_id"] = ids[0]

    gewaehlt = st.sidebar.selectbox(
        "Aktives Profil",
        ids,
        index=ids.index(st.session_state["profil_id"]),
        format_func=lambda kennung: namen[kennung],
    )
    if gewaehlt != st.session_state["profil_id"]:
        st.session_state["profil_id"] = gewaehlt
        st.session_state["ansicht"] = "uebersicht"
        st.rerun()

    st.sidebar.divider()


profilwahl()

# url_path ausdrücklich setzen: beide Seitenfunktionen heißen seite, sonst
# leitet Streamlit denselben Pfad ab und bricht ab.
navigation = st.navigation(
    [
        st.Page(
            profil.seite,
            title="Profilverwaltung",
            icon="👤",
            url_path="profil",
            default=True,
        ),
        st.Page(mahlzeiten.seite, title="Mahlzeiten", icon="🍽️", url_path="mahlzeiten"),
        st.Page(aktivitaet.seite, title="Aktivität", icon="🏃", url_path="aktivitaet"),
        st.Page(gewicht.seite, title="Gewicht", icon="⚖️", url_path="gewicht"),
    ]
)
navigation.run()
