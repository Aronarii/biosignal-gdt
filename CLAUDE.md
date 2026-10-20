# CLAUDE.md

Projektkontext für Claude Code.

- Zweck: Demo, wie ein Messgerät per GDT 2.1 (Satzarten 6302 → 6310) mit einer Praxissoftware zusammenarbeitet. Kein Medizinprodukt.
- Sprache im Code und in Texten: Deutsch (Fachbegriffe wie GDT, HRV, RMSSD bleiben).
- Tests: `python -m unittest discover -s tests -t .` muss grün sein, bevor etwas committet wird.
- GDT-Regeln: Zeile = 3-stellige Länge (Bytes, inkl. Kopf und CRLF) + 4-stellige Feldkennung + Inhalt + CRLF. 8000 zuerst, 8100 direkt danach, 8100 = Gesamtlänge in Bytes. Kodierung laut 9206 (2 = CP437, Standard; 3 = ANSI/Windows-1252).
- Keine echten Patientendaten ins Repository.
- Signalverarbeitung einfach und erklärbar halten; jede neue Kennzahl braucht einen Test mit bekanntem Sollwert.
