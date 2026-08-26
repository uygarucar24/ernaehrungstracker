# Ernährungs- und Bewegungstracker

Lokale Streamlit-Anwendung, Python, Speicherung in SQLite.
Nährwertquelle: Bundeslebensmittelschlüssel 4.0 des Max Rubner-Instituts.
Kein Cloud-Dienst, keine Nutzerkonten. Die App läuft ausschließlich lokal.

## Regeln, die immer gelten

1. **Unbekannt ist nicht null.** Fehlt ein Nährwert in der Quelle (Strich, TR, Angabe
   unterhalb der Nachweisgrenze), wird KEINE Zeile in `naehrwert` angelegt. Niemals 0
   einsetzen. Textmarker gehören nie in numerische Spalten.
2. **Abdeckung ausweisen.** Bei jeder Nährstoffsumme wird mitgeführt, aus wie vielen der
   erfassten Lebensmittel sie stammt.
3. **Verweis statt Zahl.** Gespeichert wird Lebensmittel plus Menge, nie der berechnete
   Nährwert. Nährwerte werden bei jeder Auswertung frisch nachgeschlagen.
4. **Eine Einheit je Nährstoff.** Die Einheit steht ausschließlich in `naehrstoff`.
5. **Die App warnt, gibt aber nie Entwarnung.** Es wird immer eine Einschätzung
   ausgegeben, nie ein leeres Feld.
6. **Berechnet, nachgeschlagen oder von der KI** sind drei verschiedene Arten von Angaben
   und werden in der Anzeige getrennt dargestellt.
7. **Der Profiltyp steuert, nicht das leere Feld.** Was ein Kinderprofil sieht und was
   gerechnet wird, hängt an einer ausdrücklichen Prüfung von `typ`.
8. **CSV-Export als UTF-8 mit BOM**, sonst zerlegt Excel die Umlaute.
9. **Keine medizinischen Aussagen.** Kein "Mangel", keine Ursachen für Beschwerden.

## Datenmodell

Tabellen- und Spaltennamen ohne Umlaute schreiben (naehrstoff, groesse_cm,
unvertraeglichkeit), Anzeigetexte in der Oberfläche mit Umlauten.

### profil
| Spalte | Typ | Hinweis |
|---|---|---|
| profil_id | INTEGER PK | |
| name | TEXT | |
| geburtsdatum | DATE | Alter wird daraus berechnet, nicht gespeichert |
| geschlecht | TEXT | m / w |
| groesse_cm | REAL | |
| typ | TEXT | erwachsen / kind |
| ziel_modus | TEXT NULL | abnehmen / zunehmen / halten, bei Kinderprofilen leer |
| zielgewicht_kg | REAL NULL | leer bei Kinderprofilen und bei `halten` |
| aenderung_kg_woche | REAL NULL | Vorzeichen setzt die App aus `ziel_modus`, leer bei `halten` |

Kein Gewichtsfeld. Das bei der Anlage eingegebene Gewicht wird als erste Zeile in
`gewicht` geschrieben.

Eingegeben wird nur das Tempo ohne Vorzeichen. Die Richtung steckt allein in
`ziel_modus`, damit Ziel und Rate sich nicht widersprechen können. Beim Abnehmen muss
das Zielgewicht unter, beim Zunehmen über dem aktuellen Gewicht liegen. Ist das
Zielgewicht erreicht, stellt die Anwendung auf `halten` um und leert Zielgewicht und
Rate.

### lebensmittel
| Spalte | Typ | Hinweis |
|---|---|---|
| lebensmittel_id | INTEGER PK | |
| herkunft | TEXT | bls / eigen |
| bls_schluessel | TEXT NULL | Schlüssel aus der Originaldatei |
| bezeichnung | TEXT | |
| basis_menge_g | REAL DEFAULT 100 | |
| hersteller | TEXT NULL | |
| archiviert | INTEGER | |

### naehrstoff
| Spalte | Typ | Hinweis |
|---|---|---|
| naehrstoff_id | INTEGER PK | |
| bls_spalte | TEXT | Code aus der Komponenten-Legende, z. B. ENERCC |
| name | TEXT | |
| einheit | TEXT | führend für das gesamte System |
| gruppe | TEXT | |
| uebergeordnet_id | INTEGER NULL FK | verhindert doppeltes Summieren |

### naehrwert
| Spalte | Typ | Hinweis |
|---|---|---|
| lebensmittel_id | FK, Teil PK | |
| naehrstoff_id | FK, Teil PK | |
| wert_je_100g | REAL | rein numerisch |
| wert_herkunft | TEXT | Quellencode des BLS, bei Eigeneinträgen "verpackung" |

Keine Zeile bedeutet unbekannt. Eine Zeile mit dem Wert 0 bedeutet tatsächlich null.

### unvertraeglichkeit
| Spalte | Typ | Hinweis |
|---|---|---|
| unvertraeglichkeit_id | INTEGER PK | |
| profil_id | FK | |
| art | TEXT | zunächst nur "unvertraeglichkeit" |
| bezeichnung | TEXT | zunächst nur "laktose" |
| pruefweg | TEXT | bls / ki_hinweis |
| naehrstoff_id | FK NULL | bei Laktose der LACS-Nährstoff |
| schwelle_je_100g | REAL NULL | |
| aktiv | INTEGER | |

### gewicht
| Spalte | Typ |
|---|---|
| profil_id | FK, Teil PK |
| datum | DATE, Teil PK |
| gewicht_kg | REAL |
| notiz | TEXT NULL |

Tage ohne Eintrag bleiben leer. Nicht interpolieren.

### mahlzeit
| Spalte | Typ | Hinweis |
|---|---|---|
| mahlzeit_id | INTEGER PK | |
| profil_id | FK, Teil UNIQUE | |
| datum | DATE, Teil UNIQUE | |
| tagesabschnitt | TEXT, Teil UNIQUE | feste Werteliste, kein Freitext |

Genau eine Mahlzeit je Profil, Datum und Tagesabschnitt. Als UNIQUE-Regel in der
Datenbank hinterlegen, nicht nur im Code. Wird später etwas ergänzt, wird eine Position
an die bestehende Mahlzeit gehängt.

### mahlzeit_position
| Spalte | Typ | Hinweis |
|---|---|---|
| position_id | INTEGER PK | |
| mahlzeit_id | FK | |
| lebensmittel_id | FK | |
| menge_g | REAL | immer Gramm |
| uhrzeit | TIME NULL | |
| eingabe_original | TEXT NULL | |
| zuordnung_weg | TEXT | direkt / ki_vorschlag / manuell |

### tag_aktivitaet
| Spalte | Typ | Hinweis |
|---|---|---|
| profil_id | FK, Teil PK | |
| datum | DATE, Teil PK | |
| min_sitzend | INTEGER | MET 1,3 |
| min_stehend | INTEGER | MET 1,8 |
| min_veranstaltung | INTEGER | MET 4,0 |

Erfassung nach Haltung, nicht nach Arbeitsform. Die Anteile überschneiden sich nicht und
ergeben zusammen die Arbeitszeit.

### sportart
| Spalte | Typ | Hinweis |
|---|---|---|
| sportart_id | INTEGER PK | |
| name | TEXT | Granularität der Quelle |
| met_wert | REAL | aus dem Compendium of Physical Activities |

### sporteinheit
| Spalte | Typ |
|---|---|
| einheit_id | INTEGER PK |
| profil_id | FK |
| datum | DATE |
| sportart_id | FK |
| dauer_min | INTEGER |

### referenzwert
| Spalte | Typ | Hinweis |
|---|---|---|
| referenzwert_id | INTEGER PK | |
| naehrstoff_id | FK | |
| geschlecht | TEXT | |
| alter_von_jahre | INTEGER | Untergrenze einschließlich |
| alter_bis_jahre | INTEGER | Obergrenze ausschließlich |
| art | TEXT | empfehlung / schaetzwert / richtwert |
| bezug | TEXT | absolut / je_kg |
| wert | REAL | |
| obergrenze | REAL NULL | |
| quelle | TEXT | |
| stand | TEXT | |

### tagesbedarf
| Spalte | Typ | Hinweis |
|---|---|---|
| profil_id | FK, Teil PK | nur Erwachsenenprofile |
| datum | DATE, Teil PK | |
| gewicht_kg_verwendet | REAL | letztes bekanntes Gewicht, hier festgehalten |
| grundumsatz_kcal | REAL | |
| aktivitaet_kcal | REAL | |
| sport_kcal | REAL | Mehrverbrauch über dem Ruheumsatz |
| bedarf_kcal | REAL | |
| berechnet_am | DATETIME | |

### ki_hinweis
| Spalte | Typ | Hinweis |
|---|---|---|
| hinweis_id | INTEGER PK | |
| profil_id | FK | |
| mahlzeit_id | FK NULL | |
| anlass | TEXT | |
| modell | TEXT | |
| prompt | TEXT | |
| antwort | TEXT | |
| erzeugt_am | DATETIME | |
| nutzer_reaktion | TEXT NULL | |

## Berechnung des Tagesbedarfs

Grundumsatz nach Mifflin-St Jeor:
- Männer: 10 × Gewicht(kg) + 6,25 × Groesse(cm) − 5 × Alter + 5
- Frauen:  10 × Gewicht(kg) + 6,25 × Groesse(cm) − 5 × Alter − 161

Aktivitäts- und Sportanteil je Tätigkeit:

    (MET − 1) × Gewicht(kg) × Stunden

Der Abzug von 1 MET ist zwingend, weil der Ruheumsatz bereits im Grundumsatz enthalten
ist. Ohne ihn wird die Ruhezeit während Arbeit und Sport doppelt gezählt.

    bedarf_kcal = grundumsatz + aktivitaet_kcal + sport_kcal

KEIN PAL-Faktor. Er bildet einen Wochendurchschnitt ab und würde den Zweck der App
zunichtemachen, nämlich dass sich Bürotag und Trainingstag unterscheiden.

Kalorienziel: aenderung_kg_woche × 7000 / 7 als tägliche Differenz zum Bedarf.

Liegt für einen Tag kein Eintrag in `tag_aktivitaet` vor, wird KEIN Tagesbedarf
ausgegeben. Nicht ersatzweise nur den Grundumsatz anzeigen.

## Bewusst nicht enthalten

Nicht einbauen, auch nicht als Vorschlag:
- Protokollierung einzelner Übungen, Sätze und Wiederholungen
- Bilderkennung von Mahlzeiten
- Anbindung von Wearables
- Cloud-Speicherung, Nutzerkonten, Login
- Rezepte und zusammengesetzte Eigenkreationen
- Allergien (die Struktur ist vorbereitet, umgesetzt werden zunächst nur
  Unverträglichkeiten)

## Arbeitsweise

- Immer nur die beauftragte Aufgabe umsetzen. Keine zusätzlichen Funktionen,
  keine vorsorglichen Erweiterungen.
- Zugangsschlüssel gehören in `.env`, niemals in den Code. `.env` steht in `.gitignore`.
- Vor jeder Änderung an bestehenden Dateien kurz benennen, was geändert wird.
