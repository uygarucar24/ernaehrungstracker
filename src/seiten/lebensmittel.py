"""Seite Lebensmittel: eigene Einträge anlegen, ändern und archivieren.

Der Bundeslebensmittelschlüssel enthält allgemeine Lebensmittel, keine
Markenprodukte. Hier erfasste Einträge bekommen herkunft = eigen, keinen
BLS-Schlüssel und bei jedem Nährwert die Herkunft verpackung.

Ein nicht ausgefülltes Feld erzeugt keine Zeile in naehrwert. Unbekannt ist
nicht null; eine ausdrücklich eingetragene 0 wird dagegen gespeichert.
"""
from __future__ import annotations

import streamlit as st

from src import datenbank

# Reihenfolge und Beschriftung der Pflichtangaben, wie sie auf der Verpackung
# stehen. Energie in Kilokalorien, alles Weitere in Gramm.
DEKLARATION = (
    ("ENERCC", "Energie (kcal)"),
    ("FAT", "Fett (g)"),
    ("FASAT", "davon gesättigte Fettsäuren (g)"),
    ("CHO", "Kohlenhydrate (g)"),
    ("SUGAR", "davon Zucker (g)"),
    ("PROT625", "Eiweiß (g)"),
    ("NACL", "Salz (g)"),
)

NEU = "__neu__"


def _felder(stammdaten: dict, vorhandene: dict, schluessel: str) -> dict[str, float | None]:
    """Baut die Eingabefelder und gibt die eingetragenen Werte zurück."""
    werte: dict[str, float | None] = {}

    st.markdown("**Nährwertdeklaration je 100 Gramm**")
    st.caption(
        "Die sieben Pflichtangaben der Verpackung. Sie stehen auf jedem Produkt und "
        "werden deshalb vollständig erfasst."
    )
    # Zwei Spalten in der Reihenfolge der Verpackung, damit "Fett" und "davon
    # gesättigte Fettsäuren" sowie "Kohlenhydrate" und "davon Zucker"
    # untereinander stehen.
    spalten = st.columns(2)
    aufteilung = ((0, ("ENERCC", "FAT", "FASAT")), (1, ("CHO", "SUGAR", "PROT625", "NACL")))
    beschriftungen = dict(DEKLARATION)
    for stelle, codes in aufteilung:
        for code in codes:
            vorbelegt = vorhandene.get(code)
            werte[code] = spalten[stelle].number_input(
                beschriftungen[code],
                min_value=0.0,
                step=0.1,
                value=float(vorbelegt["wert_je_100g"]) if vorbelegt is not None else None,
                placeholder="Angabe der Verpackung",
                key=f"lm_{code}_{schluessel}",
            )

    weitere = [
        (code, zeile)
        for code, zeile in sorted(stammdaten.items(), key=lambda paar: paar[1]["naehrstoff_id"])
        if code not in dict(DEKLARATION)
    ]
    with st.expander("Weitere Nährstoffe, falls auf der Verpackung angegeben"):
        st.caption(
            "Freiwillig. Nicht ausgefüllte Felder erzeugen keine Zeile: Der Nährstoff "
            "gilt dann als unbekannt und nicht als null."
        )
        spalten = st.columns(3)
        for stelle, (code, zeile) in enumerate(weitere):
            vorbelegt = vorhandene.get(code)
            werte[code] = spalten[stelle % 3].number_input(
                f"{zeile['name']} ({zeile['einheit']})",
                min_value=0.0,
                step=0.1,
                value=float(vorbelegt["wert_je_100g"]) if vorbelegt is not None else None,
                placeholder="ohne Angabe",
                key=f"lm_{code}_{schluessel}",
            )
    return werte


def _erfassung() -> None:
    eigene = datenbank.eigene_lebensmittel()
    beschriftung = {NEU: "Neues Lebensmittel anlegen"}
    for zeile in eigene:
        zusatz = " (archiviert)" if zeile["archiviert"] else ""
        hersteller = f" · {zeile['hersteller']}" if zeile["hersteller"] else ""
        beschriftung[zeile["lebensmittel_id"]] = (
            f"{zeile['bezeichnung']}{hersteller}{zusatz}"
        )

    auswahl = st.selectbox(
        "Eintrag",
        list(beschriftung),
        format_func=lambda kennung: beschriftung[kennung],
        key="lm_auswahl",
    )
    bearbeiten = auswahl != NEU
    eintrag = datenbank.lebensmittel(auswahl) if bearbeiten else None
    vorhandene = datenbank.naehrwerte_eines_lebensmittels(auswahl) if bearbeiten else {}
    schluessel = str(auswahl)

    st.subheader("Eintrag bearbeiten" if bearbeiten else "Neues Lebensmittel")

    spalte1, spalte2 = st.columns(2)
    bezeichnung = spalte1.text_input(
        "Bezeichnung",
        value=eintrag["bezeichnung"] if eintrag is not None else "",
        key=f"lm_bezeichnung_{schluessel}",
    )
    hersteller = spalte2.text_input(
        "Hersteller",
        value=(eintrag["hersteller"] or "") if eintrag is not None else "",
        key=f"lm_hersteller_{schluessel}",
    )

    stammdaten = {
        zeile["bls_spalte"]: zeile
        for zeile in datenbank.alle_naehrstoffe()
    }
    if not stammdaten:
        st.warning(
            "Es sind keine Nährstoffe hinterlegt. Bitte zuerst "
            "`python importe/import_bls.py` ausführen."
        )
        return

    werte = _felder(stammdaten, vorhandene, schluessel)

    if bearbeiten:
        st.caption(
            "Änderungen an den Nährwerten wirken sich rückwirkend auf alle Auswertungen "
            "aus: Mahlzeiten speichern nur Lebensmittel und Menge, die Werte werden bei "
            "jeder Anzeige neu nachgeschlagen."
        )

    if st.button("Speichern", type="primary"):
        try:
            kennung = datenbank.eigenes_lebensmittel_speichern(
                bezeichnung=bezeichnung,
                hersteller=hersteller,
                werte=werte,
                lebensmittel_id=auswahl if bearbeiten else None,
            )
        except datenbank.DatenFehler as fehler:
            st.error(str(fehler))
            return
        geschrieben = sum(1 for wert in werte.values() if wert is not None)
        anzahl = datenbank.positionen_mit_lebensmittel(kennung)
        fehlende = [
            beschriftung
            for code, beschriftung in DEKLARATION
            if werte.get(code) is None
        ]
        st.session_state["lm_meldung"] = (
            f"Gespeichert: {bezeichnung.strip()} mit {geschrieben} von "
            f"{len(werte)} möglichen Nährwerten. Nicht ausgefüllte Nährstoffe "
            "bleiben ohne Zeile und gelten als unbekannt."
            + (
                f" {anzahl} bereits erfasste Position(en) verwenden diesen Eintrag; "
                "ihre Auswertung ändert sich mit."
                if anzahl
                else ""
            )
        )
        st.session_state["lm_fehlende"] = fehlende
        st.rerun()

    if meldung := st.session_state.pop("lm_meldung", None):
        st.success(meldung)
    if fehlende := st.session_state.pop("lm_fehlende", None):
        # Diese Angaben stehen auf jeder Verpackung; fehlen sie, entsteht eine
        # Lücke, die sich in den Auswertungen als geringere Abdeckung zeigt.
        st.warning(
            "Ohne Angabe geblieben sind Pflichtangaben der Nährwertdeklaration: "
            + ", ".join(fehlende)
            + ". Sie stehen auf jeder Verpackung und lassen sich nachtragen."
        )


def _verwaltung() -> None:
    st.subheader("Eigene Lebensmittel")

    eigene = datenbank.eigene_lebensmittel()
    if not eigene:
        st.info("Es sind noch keine eigenen Lebensmittel erfasst.")
        return

    breiten = [3.0, 2.0, 1.4, 1.4, 1.2, 1.2]
    kopf = st.columns(breiten)
    for spalte, titel in zip(
        kopf, ("Bezeichnung", "Hersteller", "Nährwerte", "Verwendung", "", "")
    ):
        spalte.caption(titel)

    for zeile in eigene:
        kennung = zeile["lebensmittel_id"]
        anzahl_werte = len(datenbank.naehrwerte_eines_lebensmittels(kennung))
        verwendet = datenbank.positionen_mit_lebensmittel(kennung)
        spalten = st.columns(breiten)
        spalten[0].write(
            zeile["bezeichnung"] + (" *(archiviert)*" if zeile["archiviert"] else "")
        )
        spalten[1].write(zeile["hersteller"] or "–")
        spalten[2].write(f"{anzahl_werte} Angaben")
        spalten[3].write(f"{verwendet} Position(en)")
        if zeile["archiviert"]:
            if spalten[4].button("Aktivieren", key=f"lm_aktiv_{kennung}"):
                datenbank.lebensmittel_archivieren(kennung, False)
                st.rerun()
        elif spalten[4].button("Archivieren", key=f"lm_arch_{kennung}"):
            datenbank.lebensmittel_archivieren(kennung, True)
            st.rerun()
        if verwendet == 0:
            if spalten[5].button("Löschen", key=f"lm_del_{kennung}"):
                try:
                    datenbank.eigenes_lebensmittel_loeschen(kennung)
                except datenbank.DatenFehler as fehler:
                    st.error(str(fehler))
                    return
                st.rerun()
        else:
            spalten[5].caption("in Verwendung")

    st.caption(
        "Archivierte Einträge erscheinen nicht mehr in der Suche, bleiben aber "
        "erhalten, damit früher erfasste Mahlzeiten auswertbar bleiben. Gelöscht "
        "werden kann nur, worauf keine Position verweist."
    )


# --------------------------------------------------------------------------- #
# Seite
# --------------------------------------------------------------------------- #
def seite() -> None:
    st.title("Lebensmittel")
    st.caption(
        "Für Produkte, die der Bundeslebensmittelschlüssel nicht führt. Eigene Einträge "
        "erscheinen in der Suche neben denen aus dem Datenbestand und sind dort als "
        "eigene gekennzeichnet."
    )

    _erfassung()
    st.divider()
    _verwaltung()
