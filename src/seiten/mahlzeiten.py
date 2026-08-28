"""Seite Mahlzeiten: Positionen erfassen und die Mahlzeit auswerten.

Gespeichert werden ausschließlich Lebensmittel und Menge. Die Nährwerte werden
bei jeder Anzeige frisch aus naehrwert geholt und auf die Menge umgerechnet.
"""
from __future__ import annotations

from datetime import date

import streamlit as st

from src import datenbank

ABSCHNITT_ANZEIGE = {
    "fruehstueck": "Frühstück",
    "mittag": "Mittagessen",
    "abend": "Abendessen",
    "snack": "Snack",
}

# Angezeigte Nährstoffe. Der Name kommt hier aus der Anzeige, die Einheit
# ausschließlich aus der Tabelle naehrstoff.
ANZEIGE_NAEHRSTOFFE = (
    ("ENERCC", "Energie"),
    ("PROT625", "Eiweiß"),
    ("FAT", "Fett"),
    ("CHO", "Kohlenhydrate"),
    ("SUGAR", "Zucker"),
)
CODES = tuple(code for code, _ in ANZEIGE_NAEHRSTOFFE)

SPALTENBREITEN = [3.2, 1.0, 1.1, 1.0, 1.0, 1.4, 1.0, 0.7]


def _zahl(wert: float, einheit: str) -> str:
    """Kilokalorien ohne Nachkommastelle, Gramm mit einer."""
    return f"{wert:.0f} {einheit}" if einheit == "kcal" else f"{wert:.1f} {einheit}"


def _treffer_text(zeile) -> str:
    if zeile["kcal_je_100g"] is None:
        return f"{zeile['bezeichnung']} — Energie unbekannt"
    return f"{zeile['bezeichnung']} — {zeile['kcal_je_100g']:.0f} kcal/100 g"


# --------------------------------------------------------------------------- #
# Erfassung
# --------------------------------------------------------------------------- #
def _erfassung(profil_id: int, datum: date, tagesabschnitt: str) -> None:
    st.subheader("Lebensmittel hinzufügen")

    if datenbank.lebensmittel_anzahl() == 0:
        st.warning(
            "Es sind keine Lebensmittel hinterlegt. Bitte zuerst "
            "`python import_bls.py` ausführen."
        )
        return

    suchtext = st.text_input(
        "Suche in der Bezeichnung",
        key="mz_suche",
        placeholder="z. B. hafer flocken",
        help="Einfache Textsuche. Alle eingegebenen Begriffe müssen vorkommen.",
    )
    if len(suchtext.strip()) < 2:
        st.caption("Mindestens zwei Zeichen eingeben.")
        return

    treffer = datenbank.lebensmittel_suchen(suchtext)
    if not treffer:
        st.warning("Kein Lebensmittel gefunden.")
        return

    beschriftung = {zeile["lebensmittel_id"]: _treffer_text(zeile) for zeile in treffer}
    st.caption(f"{len(treffer)} Treffer, kürzeste Bezeichnungen zuerst.")

    spalte1, spalte2 = st.columns([3, 1])
    lebensmittel_id = spalte1.selectbox(
        "Treffer",
        list(beschriftung),
        format_func=lambda kennung: beschriftung[kennung],
        key="mz_treffer",
    )
    menge_g = spalte2.number_input(
        "Menge in Gramm",
        min_value=1.0,
        max_value=5000.0,
        value=100.0,
        step=10.0,
        key="mz_menge",
    )

    if st.button("Position hinzufügen", type="primary"):
        try:
            datenbank.position_hinzufuegen(
                profil_id=profil_id,
                datum=datum,
                tagesabschnitt=tagesabschnitt,
                lebensmittel_id=int(lebensmittel_id),
                menge_g=float(menge_g),
            )
        except datenbank.DatenFehler as fehler:
            st.error(str(fehler))
            return
        st.rerun()


# --------------------------------------------------------------------------- #
# Anzeige der Mahlzeit
# --------------------------------------------------------------------------- #
def _anzeige(profil_id: int, datum: date, tagesabschnitt: str) -> None:
    st.subheader(f"{ABSCHNITT_ANZEIGE[tagesabschnitt]} am {datum.strftime('%d.%m.%Y')}")

    positionen = datenbank.mahlzeit_positionen(profil_id, datum, tagesabschnitt)
    if not positionen:
        st.info("Für diesen Tagesabschnitt ist noch nichts erfasst.")
        return

    stammdaten = datenbank.naehrstoffe(CODES)
    werte = datenbank.naehrwerte([p["lebensmittel_id"] for p in positionen], CODES)

    kopf = st.columns(SPALTENBREITEN)
    kopf[0].caption("Lebensmittel")
    kopf[1].caption("Menge")
    for stelle, (code, name) in enumerate(ANZEIGE_NAEHRSTOFFE, start=2):
        kopf[stelle].caption(name)

    summen = {code: 0.0 for code in CODES}
    abdeckung = {code: 0 for code in CODES}

    for position in positionen:
        zeile = st.columns(SPALTENBREITEN)
        zeile[0].write(position["bezeichnung"])
        zeile[1].write(f"{position['menge_g']:.0f} g")

        for stelle, (code, _) in enumerate(ANZEIGE_NAEHRSTOFFE, start=2):
            wert_je_100g = werte.get((position["lebensmittel_id"], code))
            if wert_je_100g is None:
                # Unbekannt ist nicht null: kein Wert, keine 0, nicht in der Summe.
                zeile[stelle].write("unbekannt")
                continue
            wert = wert_je_100g * position["menge_g"] / datenbank.BEZUGSMENGE_G
            summen[code] += wert
            abdeckung[code] += 1
            zeile[stelle].write(_zahl(wert, stammdaten[code]["einheit"]))

        if zeile[7].button("✕", key=f"mz_loeschen_{position['position_id']}", help="Position entfernen"):
            datenbank.position_loeschen(position["position_id"])
            st.rerun()

    st.divider()

    fuss = st.columns(SPALTENBREITEN)
    fuss[0].write("**Summe**")
    fuss[1].write(f"**{sum(p['menge_g'] for p in positionen):.0f} g**")
    for stelle, (code, _) in enumerate(ANZEIGE_NAEHRSTOFFE, start=2):
        if abdeckung[code] == 0:
            fuss[stelle].write("**unbekannt**")
        else:
            fuss[stelle].write(f"**{_zahl(summen[code], stammdaten[code]['einheit'])}**")
        fuss[stelle].caption(f"aus {abdeckung[code]} von {len(positionen)}")

    if any(abdeckung[code] < len(positionen) for code in CODES):
        st.caption(
            "Fehlende Nährwerte sind als unbekannt ausgewiesen und gehen nicht "
            "in die Summe ein. Die Summe deckt dann weniger Positionen ab."
        )


# --------------------------------------------------------------------------- #
# Seite
# --------------------------------------------------------------------------- #
def seite() -> None:
    st.title("Mahlzeiten")

    profil_id = st.session_state.get("profil_id")
    if profil_id is None:
        st.info("Lege zuerst ein Profil an. Mahlzeiten hängen immer an einem Profil.")
        return

    spalte1, spalte2 = st.columns(2)
    datum = spalte1.date_input(
        "Datum",
        value=date.today(),
        format="DD.MM.YYYY",
        key="mz_datum",
    )
    tagesabschnitt = spalte2.selectbox(
        "Tagesabschnitt",
        list(datenbank.TAGESABSCHNITTE),
        format_func=lambda wert: ABSCHNITT_ANZEIGE[wert],
        key="mz_abschnitt",
    )

    _erfassung(profil_id, datum, tagesabschnitt)
    st.divider()
    _anzeige(profil_id, datum, tagesabschnitt)
