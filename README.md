# biosignal-gdt

![Tests](https://github.com/Aronarii/biosignal-gdt/actions/workflows/tests.yml/badge.svg)

Pulsanalyse mit GDT-Anbindung an die Praxissoftware: ein kleines Demo-Projekt, das zeigt, wie ein medizinisches Messgerät über die **GDT-Schnittstelle** (Gerätedatenträger, Version 2.1) mit einer Praxisverwaltungssoftware zusammenarbeitet.

> Demo- und Lernprojekt. **Kein Medizinprodukt**, nicht für Diagnosen. Alle Patientendaten in `samples/` sind erfunden.

## Worum es geht

In Arztpraxen sind EKG-, Spirometrie- oder Blutdruckgeräte meist per GDT an die Praxissoftware angebunden. Der Ablauf:

```
Praxissoftware                      Gerät / Auswertung (dieses Projekt)
--------------                      -----------------------------------
Satzart 6302  "Neue Untersuchung anfordern"  ──►  liest Patient + Auftrag
                                                  wertet Pulssignal aus (PPG/EKG)
Satzart 6310  "Daten einer Untersuchung"     ◄──  schreibt Messwerte + Befundtext
```

Das Projekt

1. **liest und prüft GDT-Dateien** (Zeilenlängen, Satzlänge 8100, Pflichtfelder, Datumsformat, Zeichensatz 9206),
2. **wertet ein Pulssignal aus**: Bandpassfilter, Schlagerkennung mit Gegenprobe über die Autokorrelation, Herzfrequenz, HRV (SDNN, RMSSD) und eine **Plausibilitätsprüfung der Signalqualität**,
3. **schreibt den Ergebnis-Datensatz 6310** mit Patientendaten aus der Anforderung, Messwerten (8410/8411/8420/8421) und Befundtext (6220),
4. **prüft das eigene Ergebnis** vor der Rückgabe erneut und erstellt ein Diagramm.

![Pulsanalyse](docs/pulsanalyse.png)

## Schnellstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# GDT-Datei anzeigen und prüfen
python -m biosignal_gdt pruefen samples/anforderung_6302.gdt

# Anforderung beantworten, mit künstlichem Testsignal
python -m biosignal_gdt messen samples/anforderung_6302.gdt --synthetisch --aus ausgabe

# ... oder mit echtem Signal, z. B. PPG aus dem BIDMC-Datensatz (PhysioNet), 125 Hz
python -m biosignal_gdt messen samples/anforderung_6302.gdt --csv bidmc_01_Signals.csv --spalte PLETH --fs 125

# Validierung mit echten Daten (BIDMC-Datensatz, siehe unten)
python -m biosignal_gdt validieren daten/bidmc_csv --aus ausgabe/validierung

# Tests
python -m unittest discover -s tests -t .
```

## Aufbau

| Datei | Inhalt |
|---|---|
| `biosignal_gdt/gdt.py` | GDT lesen, schreiben, validieren; Satzlänge wird automatisch berechnet |
| `biosignal_gdt/signal.py` | Filter, Schlagerkennung, HF/HRV, Signalqualität, Testsignal |
| `biosignal_gdt/workflow.py` | Ablauf 6302 → Auswertung → 6310, Befundtext, Diagramm |
| `biosignal_gdt/validierung.py` | Vergleich mit echten Daten: Fenster, Referenz, MAE, Bland-Altman, Diagramme |
| `biosignal_gdt/cli.py` | Kommandozeile `pruefen`, `messen` und `validieren` |
| `tests/` | 21 Tests, u. a. Satzlänge, Umlaute (1 Byte in ANSI), fehlerhafte Zeilen, HF-Genauigkeit von 35 bis 150 /min, Fälle aus der Validierung |

## Designentscheidungen

- **Validierung vor und nach der Verarbeitung.** Eine fehlerhafte Anforderung wird abgelehnt, und die eigene Antwort wird vor der Rückgabe erneut geprüft. In der Praxis sind fehlerhafte Schnittstellendateien eine häufige Ursache für Supportfälle.
- **Einfache, nachvollziehbare Signalverarbeitung** statt Black Box. Bei schlechter Signalqualität wird das im Befundtext gesagt, statt einen unsicheren Wert stillschweigend zu übernehmen. Diese Erfahrung stammt aus meiner Arbeit an einem Multispektral-Photometer: Robuste, tolerante Verfahren sind im Alltag oft wertvoller als scheinbar exakte.
- **Zeichensatz bewusst behandelt** (Feld 9206: 2 = CP437, Standard ohne Angabe; 3 = ANSI/Windows-1252): Umlaute in Namen ändern die Zeilenlänge in Bytes.
- **Gegenprobe bei der Schlagerkennung.** Ein Test bei niedriger Herzfrequenz (40 /min) zeigte, dass die Nebenwelle der Pulskurve (dikrote Welle) als zusätzlicher Schlag gezählt wurde. Seitdem schätzt das Programm den Schlagabstand zusätzlich über die Autokorrelation, passt den Mindestabstand daran an und stuft die Qualität herab, wenn beide Verfahren nicht zusammenpassen. Der Fall ist als Testfall abgesichert.

## Validierung mit echten Daten

Künstliche Signale zeigen nur, dass der Code tut, was ich mir vorgestellt habe. Deshalb habe ich die Herzfrequenz-Schätzung mit echten Aufnahmen geprüft: dem **BIDMC PPG and Respiration Dataset** (PhysioNet), 53 Aufnahmen von Intensivpatienten à 8 Minuten, PPG mit 125 Hz. Als Referenz dient die Herzfrequenz, die der Patientenmonitor aus dem **EKG** bestimmt hat, also eine unabhängige Messmethode.

Vorgehen: Jede Aufnahme wird in 30-s-Fenster zerlegt (848 Fenster), für jedes Fenster wird die Herzfrequenz geschätzt und mit dem Median der Monitorwerte im selben Zeitraum verglichen.

| Signalqualität (eigene Bewertung) | Fenster | MAE [/min] | Bias [/min] | 95-%-Übereinstimmungsgrenzen [/min] | Anteil innerhalb ±5 /min |
|---|---|---|---|---|---|
| gut | 838 | 1,1 | −0,4 | −6,7 bis +5,9 | 97 % |
| eingeschränkt oder unzureichend | 10 | 24,5 | −24,5 | – | 40 % |
| alle | 848 | 1,4 | −0,7 | −10,2 bis +8,8 | 96 % |

![Bland-Altman](docs/validierung_bland_altman.png)

**Was ich aus den echten Daten gelernt habe**

- **Erster Durchlauf: MAE 3,3 /min, nur 90 % innerhalb ±5 /min.** Viele Fenster lagen bei der halben Herzfrequenz (z. B. 50 statt 110 /min). Ursache: Bei echten Signalen schwankt die Pulsamplitude von Schlag zu Schlag. Dann ist die Autokorrelation beim doppelten Schlagabstand höher als beim echten, und meine Regel gegen die dikrote Welle (aus Teil 1) hat den falschen Abstand gewählt. Lösung: zusätzliche Prüfung, ob genau bei der halben Periode ein eigener Gipfel liegt. Ein Testfall mit wechselnder Amplitude sichert das ab.
- **Systematisch etwas zu niedrige Werte.** Einzelne schwache Schläge wurden übersehen; das doppelt lange Intervall zog den Mittelwert nach unten. Die Herzfrequenz wird jetzt aus dem **Median** der Schlagabstände berechnet.
- **Die Qualitätsbewertung trennt brauchbar:** Fenster mit „gut“ liegen zu 97 % innerhalb ±5 /min, die übrigen Fenster sind deutlich unzuverlässiger. Genau dafür ist die Bewertung da: unsichere Werte kennzeichnen statt still übernehmen.
- **Nicht jede Abweichung ist ein Fehler der Pulsanalyse.** In 4 der 6 Fenster mit „gut“ und mehr als 10 /min Abweichung (Aufnahmen 39 und 41) zeigt auch die Pulsfrequenz des Pulsoximeters den niedrigeren Wert. Dort weichen EKG- und Pulsfrequenz selbst voneinander ab, z. B. weil nicht jeder Herzschlag eine messbare Pulswelle erzeugt.

**Einschränkung:** Beide Anpassungen habe ich anhand dieses Datensatzes entwickelt. Die Werte oben sind daher eher optimistisch; eine Prüfung mit einem zweiten, unabhängigen Datensatz steht noch aus.

Datenquelle: Pimentel M.A.F. et al., *Towards a Robust Estimation of Respiratory Rate from Pulse Oximeters*, IEEE TBME 64(8), 2016; Goldberger A. et al., PhysioBank, PhysioToolkit, and PhysioNet, Circulation 101(23), 2000. Lizenz ODC-By 1.0. Die Daten liegen nicht im Repository; Download unter physionet.org/content/bidmc/1.0.0 und den Ordner `bidmc_csv` nach `daten/` kopieren.

## Grenzen

- Nur die Felder, die für diesen Ablauf nötig sind, keine vollständige Umsetzung der GDT-Spezifikation.
- Die Verfahrenskennung `PULS01` (Feld 8402) ist frei gewählt; in echten Systemen wird sie pro Gerät konfiguriert.
- Keine Dateiüberwachung (Austauschordner), keine Anbindung an eine echte Praxissoftware; der Dateiname folgt nicht der üblichen GDT-Benennung aus Empfänger- und Senderkürzel.
- Zeichensatz 1 (DIN 66003) wird vereinfacht als ASCII gelesen.
- Validiert mit ruhenden Intensivpatienten (BIDMC); Bewegungsartefakte, wie bei Wearables, sind nicht geprüft.

## Wie das Projekt entstanden ist

Entwickelt mit **Claude Code** (agentische KI-Programmierung). Die Ergebnisse habe ich geprüft und den Code durchgearbeitet. Die GDT-Grundlagen habe ich anhand öffentlicher Beschreibungen von Geräteherstellern geprüft.

Nächste Schritte, die ich mir vorgenommen habe: Austauschordner überwachen, Satzart 6311 (Daten zeigen), Ausgabe zusätzlich als HL7-FHIR-`Observation`.

---
Aron Dunai-Kovács · B.Eng. Medizintechnik (EAH Jena)
