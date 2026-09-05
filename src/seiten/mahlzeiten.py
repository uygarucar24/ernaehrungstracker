"""Seite Mahlzeiten: Positionen erfassen und die Mahlzeit auswerten.

Gespeichert werden ausschließlich Lebensmittel und Menge. Die Nährwerte werden
bei jeder Anzeige frisch aus naehrwert geholt und auf die Menge umgerechnet.
"""
from __future__ import annotations

from datetime import date

import streamlit as st

from src import berechnung, datenbank

# Die Beschriftung steht in datenbank.py neben der Werteliste, damit Oberfläche
# und Export sie nicht getrennt führen.
ABSCHNITT_ANZEIGE = datenbank.TAGESABSCHNITT_ANZEIGE

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


def _eigener_zusatz(zeile) -> str:
    """Kennzeichnet selbst erfasste Einträge, damit die Herkunft sichtbar bleibt."""
    if zeile["herkunft"] != "eigen":
        return ""
    hersteller = zeile["hersteller"] if "hersteller" in zeile.keys() else None
    return f" · eigener Eintrag{f', {hersteller}' if hersteller else ''}"


def _treffer_text(zeile) -> str:
    energie = (
        "Energie unbekannt"
        if zeile["kcal_je_100g"] is None
        else f"{zeile['kcal_je_100g']:.0f} kcal/100 g"
    )
    return f"{zeile['bezeichnung']} — {energie}{_eigener_zusatz(zeile)}"


# --------------------------------------------------------------------------- #
# Erfassung
# --------------------------------------------------------------------------- #
def _erfassung(profil_id: int, datum: date, tagesabschnitt: str) -> None:
    st.subheader("Lebensmittel hinzufügen")

    if datenbank.lebensmittel_anzahl() == 0:
        st.warning(
            "Es sind keine Lebensmittel hinterlegt. Bitte zuerst "
            "`python importe/import_bls.py` ausführen."
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
def _anzeige(profil_id: int, datum: date, tagesabschnitt: str) -> list:
    """Zeigt die Mahlzeit und gibt ihre Positionen zurück."""
    st.subheader(f"{ABSCHNITT_ANZEIGE[tagesabschnitt]} am {datum.strftime('%d.%m.%Y')}")

    positionen = datenbank.mahlzeit_positionen(profil_id, datum, tagesabschnitt)
    if not positionen:
        st.info("Für diesen Tagesabschnitt ist noch nichts erfasst.")
        return []

    stammdaten = datenbank.naehrstoffe(CODES)
    werte = datenbank.naehrwerte([p["lebensmittel_id"] for p in positionen], CODES)

    kopf = st.columns(SPALTENBREITEN)
    kopf[0].caption("Lebensmittel")
    kopf[1].caption("Menge")
    for stelle, (code, name) in enumerate(ANZEIGE_NAEHRSTOFFE, start=2):
        kopf[stelle].caption(name)

    # Summen und Abdeckung kommen aus berechnung.naehrwertsummen, damit die
    # Regel zur Abdeckung nur an einer Stelle steht.
    summen, abdeckung, gesamtmenge = berechnung.naehrwertsummen(
        [(p["lebensmittel_id"], p["menge_g"]) for p in positionen],
        werte,
        CODES,
        datenbank.BEZUGSMENGE_G,
    )

    for position in positionen:
        zeile = st.columns(SPALTENBREITEN)
        zeile[0].write(position["bezeichnung"] + _eigener_zusatz(position))
        zeile[1].write(f"{position['menge_g']:.0f} g")

        for stelle, (code, _) in enumerate(ANZEIGE_NAEHRSTOFFE, start=2):
            wert_je_100g = werte.get((position["lebensmittel_id"], code))
            if wert_je_100g is None:
                # Unbekannt ist nicht null: kein Wert, keine 0, nicht in der Summe.
                zeile[stelle].write("unbekannt")
                continue
            wert = berechnung.menge_je_portion(
                wert_je_100g, position["menge_g"], datenbank.BEZUGSMENGE_G
            )
            zeile[stelle].write(_zahl(wert, stammdaten[code]["einheit"]))

        if zeile[7].button("✕", key=f"mz_loeschen_{position['position_id']}", help="Position entfernen"):
            datenbank.position_loeschen(position["position_id"])
            st.rerun()

    st.divider()

    fuss = st.columns(SPALTENBREITEN)
    fuss[0].write("**Summe**")
    fuss[1].write(f"**{gesamtmenge:.0f} g**")
    for stelle, (code, _) in enumerate(ANZEIGE_NAEHRSTOFFE, start=2):
        if abdeckung[code] == 0:
            fuss[stelle].write("**unbekannt**")
        else:
            fuss[stelle].write(f"**{_zahl(summen[code], stammdaten[code]['einheit'])}**")
        fuss[stelle].caption(berechnung.abdeckungstext(abdeckung[code], gesamtmenge, kurz=True))

    st.caption(
        f"Die Prozentangabe unter der Summe ist die Abdeckung: der Anteil der erfassten "
        f"Menge von {gesamtmenge:.0f} g, für den ein Nährwert vorliegt — nicht der Anteil "
        "der Lebensmittel."
    )
    if any(abdeckung[code] < gesamtmenge for code in CODES):
        st.caption(
            "Fehlende Nährwerte sind als unbekannt ausgewiesen und gehen nicht "
            "in die Summe ein. Die Summe deckt dann weniger Menge ab."
        )
    return positionen


# --------------------------------------------------------------------------- #
# Prüfung auf Unverträglichkeiten
# --------------------------------------------------------------------------- #
def _aussage(zustand: str, stoff: str, menge: float | None, einheit: str, herkunft: str | None,
             schwelle: float | None) -> str:
    """Formuliert die Aussage je Position. Beschreibt nur den Datenbestand."""
    if zustand == berechnung.ENTHALTEN:
        return f"Enthält {stoff}: {menge:.2f} {einheit}"
    if zustand == berechnung.UNTER_SCHWELLE:
        return (
            f"Enthält {stoff}: {menge:.2f} {einheit}, unterhalb der hinterlegten "
            f"Schwelle von {schwelle:g} {einheit} je 100 g"
        )
    if zustand == berechnung.FREI_LOGISCH:
        return f"Enthält kein(e) {stoff}"
    if zustand == berechnung.FREI_ANDERE:
        return f"Enthält kein(e) {stoff} (Herkunft der Angabe: {herkunft or 'ohne Angabe'})"
    return f"Keine Angabe zu {stoff}"


def _unvertraeglichkeiten(profil_id: int, positionen: list) -> None:
    """Je Position eine Aussage zu jeder hinterlegten Unverträglichkeit.

    Die Prüfung läuft vollständig über den Datenbestand. Weitere Stoffe lassen
    sich ergänzen, indem in unvertraeglichkeit ein weiterer Eintrag mit Verweis
    auf den Nährstoff angelegt wird; hier ist nichts anzupassen.
    """
    eintraege = [
        zeile
        for zeile in datenbank.unvertraeglichkeiten(profil_id)
        if zeile["pruefweg"] == "bls" and zeile["naehrstoff_id"] is not None
    ]
    if not eintraege or not positionen:
        return

    codes = tuple(
        zeile["bls_spalte"] for zeile in eintraege if zeile["bls_spalte"] is not None
    )
    werte = datenbank.naehrwerte_mit_herkunft(
        [p["lebensmittel_id"] for p in positionen], codes
    )

    st.subheader("Unverträglichkeiten")
    breiten = [2.6, 1.0, 4.4]

    for eintrag in eintraege:
        code = eintrag["bls_spalte"]
        if code is None:
            continue
        stoff = eintrag["naehrstoff_name"] or eintrag["bezeichnung"].capitalize()
        einheit = eintrag["einheit"] or ""
        schwelle = eintrag["schwelle_je_100g"]

        st.markdown(f"**{stoff}**")
        kopf = st.columns(breiten)
        for spalte, text in zip(kopf, ("Lebensmittel", "Menge", "Angabe im Datenbestand")):
            spalte.caption(text)

        summe = 0.0
        mit_wert = 0
        ohne_angabe = 0
        for position in positionen:
            zeile = werte.get((position["lebensmittel_id"], code))
            wert = zeile["wert_je_100g"] if zeile is not None else None
            herkunft = zeile["wert_herkunft"] if zeile is not None else None
            zustand = berechnung.unvertraeglichkeit_zustand(wert, herkunft, schwelle)

            menge = None
            if wert is not None:
                menge = berechnung.menge_je_portion(
                    wert, position["menge_g"], datenbank.BEZUGSMENGE_G
                )
                mit_wert += 1
                summe += menge
            if zustand == berechnung.OHNE_ANGABE:
                ohne_angabe += 1

            spalten = st.columns(breiten)
            spalten[0].write(position["bezeichnung"] + _eigener_zusatz(position))
            spalten[1].write(f"{position['menge_g']:.0f} g")
            text = _aussage(zustand, stoff, menge, einheit, herkunft, schwelle)
            if zustand == berechnung.OHNE_ANGABE:
                spalten[2].warning(text, icon="❔")
            elif zustand in (berechnung.ENTHALTEN, berechnung.UNTER_SCHWELLE):
                spalten[2].warning(text, icon="⚠️")
            else:
                spalten[2].write(text)

        st.caption(
            f"Enthaltene Menge über alle Positionen: {summe:.2f} {einheit}, "
            f"ermittelt aus {mit_wert} von {len(positionen)} Positionen. "
            + (
                f"{ohne_angabe} Position(en) ohne Angabe gehen nicht in die Summe ein."
                if ohne_angabe
                else "Für alle Positionen liegt eine Angabe vor."
            )
        )

    st.caption(
        "Die Angaben stammen aus dem hinterlegten Datenbestand und beschreiben nur, "
        "was dort steht. Maßgeblich ist die Deklaration auf der Verpackung."
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
    positionen = _anzeige(profil_id, datum, tagesabschnitt)
    if positionen:
        st.divider()
        _unvertraeglichkeiten(profil_id, positionen)
