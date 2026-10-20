"""Lesen, Schreiben und Prüfen von GDT-Datensätzen (Gerätedatenträger, Version 2.1).

GDT ist die Schnittstelle, über die medizinische Geräte in Deutschland Daten mit
der Praxissoftware austauschen. Ein Datensatz besteht aus Zeilen der Form

    LLLFFFFInhalt<CR><LF>

    LLL   = Länge der gesamten Zeile in Bytes (3-stellig, inkl. LLL, FFFF und CRLF)
    FFFF  = Feldkennung (4-stellig), z. B. 8000 = Satzart
    Inhalt = Feldinhalt in der vereinbarten Zeichenkodierung (Feld 9206; fehlt es, gilt CP437)

Feld 8100 enthält die Länge des gesamten Datensatzes in Bytes (5-stellig).
"""

from __future__ import annotations

from dataclasses import dataclass, field

CRLF = b"\r\n"
LINE_OVERHEAD = 3 + 4 + 2  # Länge + Feldkennung + CRLF

# Zeichensatz-Codes aus Feld 9206 (GDT 2.1):
#   1 = 7-Bit-Code nach DIN 66003 (hier vereinfacht als ASCII gelesen)
#   2 = IBM-Zeichensatz CP437 (Standard, wenn 9206 fehlt)
#   3 = ANSI / Windows-1252
ENCODINGS = {"1": "ascii", "2": "cp437", "3": "cp1252"}
STANDARD_ENCODING = "cp437"

SATZARTEN = {
    "6301": "Stammdaten übermitteln",
    "6302": "Neue Untersuchung anfordern",
    "6310": "Daten einer Untersuchung übermitteln",
    "6311": "Daten einer Untersuchung zeigen",
}

FELDNAMEN = {
    "8000": "Satzart",
    "8100": "Satzlänge",
    "8315": "GDT-ID Empfänger",
    "8316": "GDT-ID Sender",
    "9206": "Zeichensatz",
    "9218": "GDT-Version",
    "3000": "Patientennummer",
    "3101": "Name",
    "3102": "Vorname",
    "3103": "Geburtsdatum",
    "3110": "Geschlecht",
    "6200": "Tag der Speicherung",
    "6201": "Uhrzeit der Speicherung",
    "6220": "Befund",
    "6227": "Kommentar",
    "8402": "Geräte- und verfahrensspezifisches Kennfeld",
    "8410": "Test-Ident",
    "8411": "Testbezeichnung",
    "8420": "Ergebnis-Wert",
    "8421": "Einheit",
}

# Pflichtfelder, die wir für die jeweilige Satzart prüfen
PFLICHTFELDER = {
    "6302": ["8000", "8100", "3000"],
    "6310": ["8000", "8100", "3000", "8402"],
}


class GdtError(ValueError):
    """Fehler beim Lesen eines GDT-Datensatzes."""


@dataclass
class GdtRecord:
    """Ein GDT-Datensatz als geordnete Liste von (Feldkennung, Inhalt)."""

    fields: list[tuple[str, str]] = field(default_factory=list)
    encoding: str = "cp1252"

    # --- Zugriff -----------------------------------------------------------
    def get(self, kennung: str, default: str | None = None) -> str | None:
        for k, v in self.fields:
            if k == kennung:
                return v
        return default

    def get_all(self, kennung: str) -> list[str]:
        return [v for k, v in self.fields if k == kennung]

    @property
    def satzart(self) -> str | None:
        return self.get("8000")

    def add(self, kennung: str, inhalt: str | int | float) -> "GdtRecord":
        if not (len(kennung) == 4 and kennung.isdigit()):
            raise ValueError(f"Feldkennung muss 4-stellig numerisch sein: {kennung!r}")
        self.fields.append((kennung, str(inhalt)))
        return self

    # --- Schreiben ---------------------------------------------------------
    def _encode_line(self, kennung: str, inhalt: str) -> bytes:
        body = inhalt.encode(self.encoding)
        laenge = len(body) + LINE_OVERHEAD
        if laenge > 999:
            raise ValueError(f"Zeile zu lang für GDT ({laenge} Bytes): Feld {kennung}")
        return f"{laenge:03d}{kennung}".encode("ascii") + body + CRLF

    def to_bytes(self) -> bytes:
        """Serialisiert den Satz; Feld 8100 (Satzlänge) wird automatisch berechnet."""
        ohne_laenge = [(k, v) for k, v in self.fields if k != "8100"]
        if not ohne_laenge or ohne_laenge[0][0] != "8000":
            raise ValueError("Der erste Eintrag muss Feld 8000 (Satzart) sein.")
        zeilen = [self._encode_line(k, v) for k, v in ohne_laenge]
        laenge_8100_zeile = LINE_OVERHEAD + 5
        gesamt = sum(len(z) for z in zeilen) + laenge_8100_zeile
        zeile_8100 = self._encode_line("8100", f"{gesamt:05d}")
        # 8100 steht direkt hinter 8000
        return zeilen[0] + zeile_8100 + b"".join(zeilen[1:])

    # --- Lesen -------------------------------------------------------------
    @classmethod
    def from_bytes(cls, data: bytes, encoding: str | None = None) -> "GdtRecord":
        """Liest einen Datensatz. Die Kodierung wird aus Feld 9206 erkannt."""
        roh = [z for z in data.split(CRLF) if z]
        if not roh:
            raise GdtError("Leere Datei")
        # Feld 9206 zuerst in ASCII suchen, um die Kodierung zu bestimmen
        if encoding is None:
            encoding = STANDARD_ENCODING
            for z in roh:
                if z[3:7] == b"9206":
                    encoding = ENCODINGS.get(z[7:].decode("ascii", "replace").strip(), STANDARD_ENCODING)
                    break
        rec = cls(encoding=encoding)
        for nr, z in enumerate(roh, start=1):
            if len(z) < 7 or not z[:7].isdigit():
                raise GdtError(f"Zeile {nr}: ungültiger Zeilenkopf {z[:7]!r}")
            rec.fields.append((z[3:7].decode("ascii"), z[7:].decode(encoding)))
        return rec

    @classmethod
    def from_file(cls, pfad) -> "GdtRecord":
        with open(pfad, "rb") as f:
            return cls.from_bytes(f.read())

    def write(self, pfad) -> None:
        with open(pfad, "wb") as f:
            f.write(self.to_bytes())


def validate(data: bytes) -> list[str]:
    """Prüft einen GDT-Datensatz und gibt eine Liste gefundener Probleme zurück.

    Geprüft werden: Zeilenaufbau, Zeilenlängen, Satzlänge (8100), Reihenfolge
    von 8000/8100 und die Pflichtfelder der Satzart.
    """
    probleme: list[str] = []
    if not data.endswith(CRLF):
        probleme.append("Datensatz endet nicht mit CRLF")
    zeilen = data.split(CRLF)
    if zeilen and zeilen[-1] == b"":
        zeilen = zeilen[:-1]
    if not zeilen:
        return ["Leere Datei"]

    for nr, z in enumerate(zeilen, start=1):
        if len(z) < 7 or not z[:7].isdigit():
            probleme.append(f"Zeile {nr}: Kopf muss 3-stellige Länge + 4-stellige Feldkennung sein")
            continue
        angegeben = int(z[:3])
        tatsaechlich = len(z) + len(CRLF)
        if angegeben != tatsaechlich:
            probleme.append(
                f"Zeile {nr} (Feld {z[3:7].decode()}): Länge {angegeben} angegeben, {tatsaechlich} tatsächlich"
            )

    try:
        rec = GdtRecord.from_bytes(data)
    except GdtError as e:
        return probleme + [str(e)]

    if rec.fields[0][0] != "8000":
        probleme.append("Erstes Feld ist nicht 8000 (Satzart)")
    if len(rec.fields) > 1 and rec.fields[1][0] != "8100":
        probleme.append("Zweites Feld ist nicht 8100 (Satzlänge)")

    satzlaenge = rec.get("8100")
    if satzlaenge is not None:
        if not satzlaenge.isdigit():
            probleme.append(f"Feld 8100 ist nicht numerisch: {satzlaenge!r}")
        elif int(satzlaenge) != len(data):
            probleme.append(f"Satzlänge 8100 = {int(satzlaenge)}, Datei hat {len(data)} Bytes")

    satzart = rec.satzart
    if satzart not in SATZARTEN:
        probleme.append(f"Unbekannte Satzart: {satzart!r}")
    for pflicht in PFLICHTFELDER.get(satzart or "", []):
        if rec.get(pflicht) is None:
            probleme.append(f"Pflichtfeld {pflicht} ({FELDNAMEN.get(pflicht, '?')}) fehlt")

    geburt = rec.get("3103")
    if geburt is not None and not (len(geburt) == 8 and geburt.isdigit()):
        probleme.append(f"Geburtsdatum 3103 nicht im Format TTMMJJJJ: {geburt!r}")
    return probleme


def describe(rec: GdtRecord) -> str:
    """Lesbare Darstellung eines Datensatzes (für die Kommandozeile)."""
    zeilen = [f"Satzart {rec.satzart}: {SATZARTEN.get(rec.satzart or '', 'unbekannt')}"]
    for k, v in rec.fields:
        zeilen.append(f"  {k}  {FELDNAMEN.get(k, ''):<45} {v}")
    return "\n".join(zeilen)
