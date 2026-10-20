"""Der eigentliche Ablauf: Anforderung (6302) -> Messung -> Ergebnis (6310) + Diagramm."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .gdt import GdtRecord  # noqa: E402
from .signal import Ergebnis  # noqa: E402

SENDER_ID = "BSGDT01"
VERFAHREN = "PULS01"  # Verfahrenskennung (8402); in echten Systemen pro Gerät konfiguriert


def _fmt(x: float, nachkomma: int = 0) -> str:
    return "n/a" if np.isnan(x) else f"{x:.{nachkomma}f}".replace(".", ",")


def befundtext(e: Ergebnis) -> list[str]:
    zeilen = [
        f"Pulsanalyse über {e.dauer_s:.0f} s, {e.n_schlaege} Schläge erkannt.",
        f"Mittlere Herzfrequenz {_fmt(e.hf_mittel)} /min (min {_fmt(e.hf_min)}, max {_fmt(e.hf_max)}).",
        f"HRV: SDNN {_fmt(e.sdnn_ms)} ms, RMSSD {_fmt(e.rmssd_ms)} ms.",
        f"Signalqualität: {e.qualitaet} ({e.anteil_plausibel * 100:.0f} % plausible Intervalle).",
    ]
    if e.qualitaet != "gut":
        zeilen.append("Hinweis: Messung bei unzureichender Qualität bitte wiederholen.")
    return zeilen


def antwort_6310(anforderung: GdtRecord, e: Ergebnis, zeitpunkt: datetime | None = None) -> GdtRecord:
    """Erzeugt den Ergebnis-Datensatz 6310 zu einer Anforderung 6302."""
    zeitpunkt = zeitpunkt or datetime.now()
    r = GdtRecord(encoding="cp1252")
    r.add("8000", "6310")
    # Empfänger = bisheriger Sender (die Praxissoftware)
    if anforderung.get("8316"):
        r.add("8315", anforderung.get("8316"))
    r.add("8316", SENDER_ID)
    r.add("9206", "3")       # ANSI / Windows-1252
    r.add("9218", "02.10")
    for feld in ("3000", "3101", "3102", "3103", "3110"):
        wert = anforderung.get(feld)
        if wert:
            r.add(feld, wert)
    r.add("6200", zeitpunkt.strftime("%d%m%Y"))
    r.add("6201", zeitpunkt.strftime("%H%M%S"))
    r.add("8402", VERFAHREN)
    for ident, name, wert, einheit, nk in [
        ("HF", "Herzfrequenz mittel", e.hf_mittel, "/min", 0),
        ("SDNN", "HRV SDNN", e.sdnn_ms, "ms", 0),
        ("RMSSD", "HRV RMSSD", e.rmssd_ms, "ms", 0),
        ("QUAL", "Anteil plausible RR-Intervalle", e.anteil_plausibel * 100, "%", 0),
    ]:
        r.add("8410", ident).add("8411", name).add("8420", _fmt(wert, nk)).add("8421", einheit)
    for zeile in befundtext(e):
        r.add("6220", zeile)
    r.add("6227", "Demo-Software, kein Medizinprodukt. Nicht für Diagnosen verwenden.")
    return r


def diagramm(sig: np.ndarray, e: Ergebnis, pfad: Path, sekunden: float = 15.0) -> None:
    n = int(min(sekunden, e.dauer_s) * e.fs)
    t = np.arange(n) / e.fs
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 5), height_ratios=[2, 1])
    ax1.plot(t, e.gefiltert[:n], lw=1, label="gefiltert (0,5–8 Hz)")
    p = e.peaks[e.peaks < n]
    ax1.plot(p / e.fs, e.gefiltert[p], "o", ms=4, label="erkannte Schläge")
    ax1.set_xlabel("Zeit (s)")
    ax1.set_title(f"Pulsanalyse: HF {_fmt(e.hf_mittel)} /min, Qualität {e.qualitaet}")
    ax1.legend(loc="upper right", fontsize=8)
    rr = np.diff(e.peaks) / e.fs * 1000
    ax2.plot(rr, ".-", lw=1)
    ax2.set_ylabel("RR (ms)")
    ax2.set_xlabel("Schlag Nr.")
    fig.tight_layout()
    fig.savefig(pfad, dpi=120)
    plt.close(fig)
