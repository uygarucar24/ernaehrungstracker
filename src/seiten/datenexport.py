"""Seite Datenexport: erfasste Daten eines Zeitraums als ZIP herunterladen.

Reine Datenausgabe für die Weiterverwendung außerhalb der Anwendung. Es werden
keine Einstufungen, Bewertungen oder Empfehlungen exportiert.

Der Export wird auf Knopfdruck zusammengestellt und nicht bei jedem Neuaufbau
der Seite: das Lesen des Tagesbedarfs schreibt ihn zugleich neu, das soll nicht
unbemerkt für jeden Tag eines langen Zeitraums geschehen.
"""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from src import datenbank, export

# Vorbelegter Zeitraum: der laufende Monat bis heute.
VORLAUF_TAGE = 30

SCHLUESSEL = "ex_ergebnis"


def _zusammenstellen(profil_id: int, von: date, bis: date) -> None:
    try:
        daten, inhalte = export.als_zip(profil_id, von, bis)
    except datenbank.DatenFehler as fehler:
        st.error(str(fehler))
        return
    eintrag = datenbank.profil(profil_id)
    st.session_state[SCHLUESSEL] = {
        "kennung": (profil_id, von.isoformat(), bis.isoformat()),
        "daten": daten,
        "dateiname": export.dateiname(eintrag["name"], von, bis),
        "inhalte": inhalte,
    }


def _ergebnis(kennung: tuple) -> None:
    """Zeigt den fertigen Export mit seinem Umfang und bietet ihn zum Laden an."""
    ergebnis = st.session_state.get(SCHLUESSEL)
    if ergebnis is None:
        return
    if ergebnis["kennung"] != kennung:
        # Profil oder Zeitraum wurden gewechselt: der alte Stand passt nicht mehr.
        st.caption("Der Zeitraum wurde geändert. Bitte den Export neu zusammenstellen.")
        return

    st.subheader("Umfang")
    breiten = [2.2, 5.0]
    kopf = st.columns(breiten)
    for spalte, titel in zip(kopf, ("Datei", "Inhalt")):
        spalte.caption(titel)
    for name, _, beschreibung in ergebnis["inhalte"]:
        zeile = st.columns(breiten)
        zeile[0].write(name)
        zeile[1].write(beschreibung)

    st.download_button(
        "ZIP herunterladen",
        data=ergebnis["daten"],
        file_name=ergebnis["dateiname"],
        mime="application/zip",
        type="primary",
    )
    st.caption(f"{len(ergebnis['daten']) / 1024:.1f} kB, Dateiname {ergebnis['dateiname']}.")


# --------------------------------------------------------------------------- #
# Seite
# --------------------------------------------------------------------------- #
def seite() -> None:
    st.title("Datenexport")
    st.caption(
        "Gibt die erfassten Daten eines Zeitraums aus, damit sie außerhalb der Anwendung "
        "weiterverwendet werden können. Der Export enthält keine Einstufungen und keine "
        "Empfehlungen."
    )

    profil_id = st.session_state.get("profil_id")
    if profil_id is None:
        st.info("Lege zuerst ein Profil an. Der Export hängt immer an einem Profil.")
        return

    eintrag = datenbank.profil(profil_id)
    heute = date.today()

    spalte1, spalte2 = st.columns(2)
    von = spalte1.date_input(
        "Von", value=heute - timedelta(days=VORLAUF_TAGE), format="DD.MM.YYYY", key="ex_von"
    )
    bis = spalte2.date_input("Bis", value=heute, format="DD.MM.YYYY", key="ex_bis")

    if von > bis:
        st.error("Der Zeitraum beginnt nach seinem Ende.")
        return
    st.caption(
        f"Zeitraum {von.strftime('%d.%m.%Y')} bis {bis.strftime('%d.%m.%Y')}, "
        f"{(bis - von).days + 1} Tage. Beide Tage sind eingeschlossen."
    )

    # Ausdrückliche Prüfung des Profiltyps: Kinderprofile bekommen weder
    # Kalorienbilanz noch Zielwerte, die Datei dazu wird nicht aufgebaut.
    if eintrag is not None and eintrag["typ"] == "kind":
        st.caption(
            "Kinderprofil: ohne Kalorienbilanz und ohne Zielwerte. Mahlzeiten, Aktivität "
            "und Gewicht werden vollständig ausgegeben."
        )

    if st.button("Export zusammenstellen", type="primary"):
        _zusammenstellen(profil_id, von, bis)

    _ergebnis((profil_id, von.isoformat(), bis.isoformat()))

    st.divider()
    st.subheader("Aufbau der Dateien")
    st.markdown(
        "- CSV, UTF-8 mit BOM, Komma als Feldtrennzeichen, Punkt als Dezimaltrennzeichen, "
        "Datum als JJJJ-MM-TT.\n"
        "- **Ein leeres Feld bedeutet: kein Wert vorhanden.** Es ist nicht als 0 zu lesen. "
        "Das gilt für fehlende Nährwerte ebenso wie für Tage ohne Aktivitätseintrag, für "
        "die es keinen Tagesbedarf gibt.\n"
        "- Zu jedem Nährwert steht die Herkunft daneben, also der Quellencode des "
        "Bundeslebensmittelschlüssels oder `verpackung` bei selbst erfassten Lebensmitteln.\n"
        "- Die Nährwerte sind auf die erfasste Menge umgerechnet, also dieselben Werte, "
        "die die Anwendung anzeigt."
    )
    st.caption(
        "In Excel über Daten → Aus Text/CSV öffnen und als Dezimaltrennzeichen den Punkt "
        "wählen; beim Doppelklick nimmt Excel sonst die Einstellung des Systems."
    )
