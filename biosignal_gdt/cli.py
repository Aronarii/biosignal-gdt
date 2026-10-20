"""Kommandozeile.

Beispiele:
    python -m biosignal_gdt pruefen samples/anforderung_6302.gdt
    python -m biosignal_gdt messen samples/anforderung_6302.gdt --synthetisch --aus ausgabe
    python -m biosignal_gdt messen anforderung.gdt --csv bidmc_01_Signals.csv --spalte PLETH --fs 125
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .gdt import GdtRecord, describe, validate
from .signal import auswerten, lade_csv, synthetisches_ppg
from .workflow import antwort_6310, diagramm


def cmd_pruefen(args) -> int:
    data = Path(args.datei).read_bytes()
    probleme = validate(data)
    print(describe(GdtRecord.from_bytes(data)))
    print()
    if probleme:
        print(f"{len(probleme)} Problem(e) gefunden:")
        for p in probleme:
            print(f"  - {p}")
        return 1
    print("Datensatz ist formal gültig.")
    return 0


def cmd_messen(args) -> int:
    anf_bytes = Path(args.anforderung).read_bytes()
    probleme = validate(anf_bytes)
    if probleme:
        print("Anforderung ist ungültig:", *probleme, sep="\n  - ")
        return 1
    anforderung = GdtRecord.from_bytes(anf_bytes)
    if anforderung.satzart != "6302":
        print(f"Erwartet Satzart 6302, gefunden {anforderung.satzart}")
        return 1

    if args.csv:
        sig = lade_csv(args.csv, args.spalte)
    else:
        sig = synthetisches_ppg(fs=args.fs, dauer_s=60, hf=args.hf)
    ergebnis = auswerten(sig, args.fs)

    aus = Path(args.aus)
    aus.mkdir(parents=True, exist_ok=True)
    antwort = antwort_6310(anforderung, ergebnis)
    gdt_pfad = aus / "ergebnis_6310.gdt"
    antwort.write(gdt_pfad)
    diagramm(sig, ergebnis, aus / "pulsanalyse.png")

    pruefung = validate(gdt_pfad.read_bytes())
    print(describe(GdtRecord.from_file(gdt_pfad)))
    print()
    print(f"Geschrieben: {gdt_pfad} und {aus / 'pulsanalyse.png'}")
    print("Selbstprüfung des Ergebnisses:", "gültig" if not pruefung else pruefung)
    return 0 if not pruefung else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="biosignal_gdt", description="Pulsanalyse mit GDT-Anbindung (Demo)")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("pruefen", help="GDT-Datei anzeigen und formal prüfen")
    a.add_argument("datei")
    a.set_defaults(func=cmd_pruefen)

    m = sub.add_parser("messen", help="Anforderung 6302 einlesen, Signal auswerten, Ergebnis 6310 schreiben")
    m.add_argument("anforderung")
    quelle = m.add_mutually_exclusive_group(required=True)
    quelle.add_argument("--csv", help="CSV-Datei mit Signal")
    quelle.add_argument("--synthetisch", action="store_true", help="künstliches Testsignal verwenden")
    m.add_argument("--spalte", default="PLETH", help="Signalspalte in der CSV (Standard: PLETH)")
    m.add_argument("--fs", type=float, default=125.0, help="Abtastrate in Hz (Standard: 125)")
    m.add_argument("--hf", type=float, default=72.0, help="Herzfrequenz des Testsignals")
    m.add_argument("--aus", default="ausgabe", help="Ausgabeordner")
    m.set_defaults(func=cmd_messen)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
