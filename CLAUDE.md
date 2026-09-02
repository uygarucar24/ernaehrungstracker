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
10. Bei jeder neuen Funktion ist ausdrücklich festzulegen, was im Kinderprofil davon sichtbar und erfassbar ist. Nicht sichtbare Elemente werden nicht aufgebaut, nicht ausgegraut.

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

Ein erneuter Lauf von `import_bls.py --ersetzen` **aktualisiert** vorhandene Einträge
anhand von `bls_schluessel` und ersetzt ihre Nährwerte. Die `lebensmittel_id` bleibt
erhalten, damit Verweise aus `mahlzeit_position` gültig bleiben. Einträge, die in der
neuen Ausgabe fehlen, werden auf `archiviert = 1` gesetzt, nicht gelöscht, damit alte
Mahlzeiten nachvollziehbar bleiben. Die Suche zeigt nur nicht archivierte Einträge.

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

Werteliste für `tagesabschnitt`: `fruehstueck`, `mittag`, `abend`, `snack`. Sie steht in
`datenbank.TAGESABSCHNITTE` und wird beim Schreiben geprüft. Bewusst keine CHECK-Regel in
der Tabelle, weil sich die Liste in SQLite sonst nur über einen Tabellenumbau erweitern
lässt.

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
| min_schlaf | INTEGER | MET-Schlüssel `schlaf` |
| min_sitzend | INTEGER | MET-Schlüssel `sitzend` |
| min_stehend | INTEGER | MET-Schlüssel `stehend` |
| min_veranstaltung | INTEGER | MET-Schlüssel `veranstaltung` |
| tagestyp | TEXT NULL | homeoffice / buero / veranstaltung / frei, aus der Vorlage |

Erfassung nach Haltung, nicht nach Arbeitsform. Die Anteile überschneiden sich nicht und
ergeben zusammen die Arbeitszeit. Der Tagestyp belegt sie vor (Homeoffice 420/60/0,
Büro 240/240/0, Veranstaltung 0/0/480, frei 0/0/0), bleibt aber einzeln änderbar; er wird
mitgespeichert, damit erkennbar ist, ob die Werte aus der Vorlage stammen.

**Kinderprofil:** keine Arbeitszeit. Tagestyp und die drei Haltungsfelder werden auf der
Aktivitätsseite nicht aufgebaut, die drei Spalten bleiben auf 0 und `tagestyp` leer.
Erfassbar sind Schlaf und Sporteinheiten. Die Aufteilung des Tages zeigt nur Schlaf,
Sport und Restzeit (1440 minus Schlaf minus Sport) und keine Energieangaben, weil für
Kinderprofile kein Tagesbedarf berechnet wird.

### met_grundwert
| Spalte | Typ | Hinweis |
|---|---|---|
| schluessel | TEXT PK | schlaf / sitzend / stehend / veranstaltung / alltag |
| name | TEXT | Anzeigename |
| met | REAL | einzige Quelle für diese MET-Werte |
| code | TEXT | Code der Quelle |
| quelle | TEXT | |

Befüllt aus `daten/met_grundwerte.csv` über `import_met_grundwerte.py`. **Im Code stehen
keine MET-Werte.** Fehlt ein Schlüssel, wird kein Bedarf ausgegeben, sondern der Hinweis,
den Import auszuführen.

### sportart
| Spalte | Typ | Hinweis |
|---|---|---|
| sportart_id | INTEGER PK | |
| code | TEXT UNIQUE | Code der Quelle, als Text wegen führender Nullen |
| name | TEXT | Granularität der Quelle |
| met_wert | REAL | aus dem Compendium of Physical Activities |
| quelle | TEXT | Quellencode aus der CSV |
| kategorie | TEXT | joggen / fahrrad / kraftsport, nach Codepräfix 12 / 01 / 02 |

Befüllt aus `daten/sportarten.csv` über `import_sportarten.py`. Ein zweiter Lauf
aktualisiert vorhandene Codes, statt Duplikate anzulegen. Die Oberfläche wählt in zwei
Schritten: erst die Kategorie, dann die Intensität innerhalb der Kategorie, mit
sichtbarem MET-Wert.

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

`tagesbedarf` ist ein festgehaltenes Ergebnis, keine Quelle. Damit es nicht veraltet,
rechnet **jeder Lesezugriff** (`datenbank.tagesbedarf`) aus Gewicht, Aktivität und
Sporteinheiten neu und schreibt das Ergebnis mit neuem `berechnet_am` zurück. Ändert sich
eines der drei nachträglich, steht beim nächsten Lesen bereits der neue Wert. Fällt die
Aktivität weg, wird die Zeile gelöscht.

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

Der Tag wird **vollständig** aufgeteilt. 1440 Minuten bestehen aus vier Blöcken:

1. Schlaf
2. Arbeit, aufgeteilt nach Haltung (sitzend, stehend, Veranstaltung)
3. Sport, je Sporteinheit
4. Restzeit als Rechenwert: `1440 − Schlaf − Arbeit − Sport`, MET-Schlüssel `alltag`

Die Restzeit wird nicht erfasst. Ohne sie würde die übrige Zeit mit dem Ruheumsatz
eingehen, als wäre man regungslos, und der Bedarf würde mit längerer Arbeitszeit steigen,
selbst bei sitzender Tätigkeit. Ergibt die Restzeit einen negativen Wert, wird **kein**
Bedarf ausgegeben, sondern der Hinweis, dass die erfassten Zeiten zusammen mehr als
24 Stunden ergeben.

Mehrverbrauch je Block:

    (MET − 1) × Gewicht(kg) × Stunden

Der Abzug von 1 MET ist zwingend, weil der Ruheumsatz bereits im Grundumsatz enthalten
ist. Ohne ihn wird die Zeit doppelt gezählt.

`aktivitaet_kcal` fasst Schlaf, Arbeit und Restzeit zusammen, `sport_kcal` die
Sporteinheiten.

    bedarf_kcal = grundumsatz + aktivitaet_kcal + sport_kcal

KEIN PAL-Faktor. Er bildet einen Wochendurchschnitt ab und würde den Zweck der App
zunichtemachen, nämlich dass sich Bürotag und Trainingstag unterscheiden.

Kalorienziel: aenderung_kg_woche × 7000 / 7 als tägliche Differenz zum Bedarf. Liegt es
unter dem Grundumsatz, wird der Wert unverändert angezeigt und sichtbar gekennzeichnet.
Nicht begrenzen, nicht verändern.

## Tagesübersicht

Bedarf und Aufnahme werden auf einer eigenen Seite zusammengeführt. Maßgeblich für die
Differenz ist das **Kalorienziel**, nicht der Bedarf; ohne Änderungsrate sind beide
gleich. Die Differenz wird mit Vorzeichen und in Worten ausgewiesen, als verfügbare Menge
oder als Überschreitung.

Fehlt der Eintrag in `tag_aktivitaet`, gibt es keinen Bedarf und keine Differenz. Dann
wird die Aufnahme gezeigt und der Grund genannt. Nicht ersatzweise gegen den Grundumsatz
oder einen Durchschnittswert rechnen.

Positionen ohne Kalorienwert werden gezählt und die Zahl genannt, damit erkennbar ist,
dass die Aufnahme unvollständig erfasst ist.

Ist für den Tag **keine Position** erfasst oder hat keine der Positionen einen
Kalorienwert, ist die Aufnahme unbekannt: keine Aufnahme, keine Differenz. Bedarf und
Kalorienziel werden gezeigt, dazu der Grund. Nicht mit einer Aufnahme von 0 kcal rechnen —
unbekannt ist nicht null, dieselbe Regel wie beim fehlenden Aktivitätseintrag. Auch bei
den Makronährstoffen steht dann `unbekannt` statt 0.

Auf der Gewichtsseite wird das Eingabefeld mit dem Wert des **gewählten** Datums
vorbelegt, sonst mit dem letzten Wert davor. Ein späterer Eintrag darf beim Nachtragen
nicht vorgeschlagen werden. Gibt es keinen Wert bis zu diesem Tag, bleibt das Feld leer.

**Kinderprofil:** Bedarf, Kalorienziel und Differenz entfallen vollständig und werden
nicht aufgebaut. Sichtbar sind Mahlzeiten, Tagessumme und Makronährstoffe.

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
