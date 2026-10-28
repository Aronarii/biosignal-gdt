"""Validierung der Pulsanalyse mit echten Daten (BIDMC PPG and Respiration Dataset, PhysioNet).

Idee: Das PPG-Signal jeder Aufnahme wird in Fenster (Standard 30 s) zerlegt. Für jedes
Fenster schätzt `auswerten()` die Herzfrequenz. Als Referenz dient die Herzfrequenz,
die der Patientenmonitor im selben Zeitraum ausgegeben hat (Numerics-Datei, 1 Wert/s):
- HR: aus dem EKG (unabhängige Messmethode, Hauptreferenz)
- PULSE: Pulsfrequenz des Pulsoximeters (gleiche Signalquelle wie PPG)

Vergleich: mittlere absolute Abweichung (MAE), RMSE, Bland-Altman (mittlere Differenz und
95-%-Übereinstimmungsgrenzen) sowie Anteil der Fenster innerhalb von ±5 /min, jeweils
getrennt nach der eigenen Qualitätsbewertung. So lässt sich prüfen, ob die Bewertung
„gut“ tatsächlich verlässlichere Werte kennzeichnet.

Datenquelle: Pimentel et al., IEEE TBME 2016; Goldberger et al., PhysioNet, Circulation 2000.
Lizenz der Daten: Open Data Commons Attribution (ODC-By) 1.0. Die Daten liegen nicht im Repository.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .signal import auswerten

FS_BIDMC = 125.0


@dataclass
class Fenster:
    aufnahme: str
    start_s: float
    hf_ppg: float
    hf_ref_ekg: float
    hf_ref_puls: float
    qualitaet: str

    @property
    def differenz(self) -> float:
        return self.hf_ppg - self.hf_ref_ekg


def _lese_spalten(pfad: Path) -> dict[str, np.ndarray]:
    """Liest eine BIDMC-CSV; Spaltennamen ohne Leerzeichen, leere Werte als NaN."""
    with open(pfad, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        kopf = [k.strip() for k in next(reader)]
        werte: list[list[float]] = [[] for _ in kopf]
        for zeile in reader:
            for i, x in enumerate(zeile[: len(kopf)]):
                try:
                    werte[i].append(float(x))
                except ValueError:
                    werte[i].append(np.nan)
    return {k: np.asarray(v) for k, v in zip(kopf, werte)}


def finde_aufnahmen(ordner: str | Path) -> list[tuple[str, Path, Path]]:
    """Sucht Paare aus bidmc_XX_Signals.csv und bidmc_XX_Numerics.csv (auch in Unterordnern)."""
    paare = []
    for sig in sorted(Path(ordner).rglob("bidmc_*_Signals.csv")):
        nr = sig.name.split("_")[1]
        num = sig.with_name(f"bidmc_{nr}_Numerics.csv")
        if num.exists():
            paare.append((nr, sig, num))
    return paare


def _referenz(zeit: np.ndarray, werte: np.ndarray, t0: float, t1: float) -> float:
    auswahl = werte[(zeit >= t0) & (zeit < t1)]
    auswahl = auswahl[np.isfinite(auswahl) & (auswahl > 0)]
    return float(np.median(auswahl)) if auswahl.size else float("nan")


def werte_aufnahme_aus(nr: str, signals: Path, numerics: Path,
                       fenster_s: float = 30.0, fs: float = FS_BIDMC) -> list[Fenster]:
    s = _lese_spalten(signals)
    n = _lese_spalten(numerics)
    ppg = s["PLETH"]
    zeit_n = n["Time [s]"]
    schritt = int(fenster_s * fs)
    ergebnisse = []
    for start in range(0, ppg.size - schritt + 1, schritt):
        stueck = ppg[start:start + schritt]
        if not np.all(np.isfinite(stueck)):
            continue
        t0 = start / fs
        ref_ekg = _referenz(zeit_n, n.get("HR", np.array([])), t0, t0 + fenster_s)
        ref_puls = _referenz(zeit_n, n.get("PULSE", np.array([])), t0, t0 + fenster_s)
        if np.isnan(ref_ekg):
            continue
        e = auswerten(stueck, fs)
        ergebnisse.append(Fenster(nr, t0, e.hf_mittel, ref_ekg, ref_puls, e.qualitaet))
    return ergebnisse


@dataclass
class Kennzahlen:
    n: int
    mae: float
    rmse: float
    bias: float
    loa_unten: float
    loa_oben: float
    anteil_5: float  # Anteil der Fenster mit |Abweichung| <= 5 /min


def kennzahlen(schaetzung: np.ndarray, referenz: np.ndarray) -> Kennzahlen:
    """MAE, RMSE und Bland-Altman-Kennzahlen (Bias ± 1,96 · SD der Differenzen)."""
    s, r = np.asarray(schaetzung, float), np.asarray(referenz, float)
    ok = np.isfinite(s) & np.isfinite(r)
    d = s[ok] - r[ok]
    if d.size == 0:
        nan = float("nan")
        return Kennzahlen(0, nan, nan, nan, nan, nan, nan)
    sd = float(np.std(d, ddof=1)) if d.size > 1 else 0.0
    bias = float(d.mean())
    return Kennzahlen(
        n=int(d.size),
        mae=float(np.mean(np.abs(d))),
        rmse=float(np.sqrt(np.mean(d ** 2))),
        bias=bias,
        loa_unten=bias - 1.96 * sd,
        loa_oben=bias + 1.96 * sd,
        anteil_5=float(np.mean(np.abs(d) <= 5)),
    )


def zusammenfassung(fenster: list[Fenster]) -> dict[str, Kennzahlen]:
    gruppen = {"alle": fenster}
    for q in ("gut", "eingeschränkt", "unzureichend"):
        gruppen[q] = [f for f in fenster if f.qualitaet == q]
    return {
        name: kennzahlen([f.hf_ppg for f in g], [f.hf_ref_ekg for f in g])
        for name, g in gruppen.items()
    }


def schreibe_csv(fenster: list[Fenster], pfad: Path) -> None:
    with open(pfad, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(fenster[0]).keys()) + ["differenz"])
        w.writeheader()
        for x in fenster:
            w.writerow({**asdict(x), "differenz": round(x.differenz, 2)})


def diagramme(fenster: list[Fenster], aus: Path) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    farben = {"gut": "#1b7837", "eingeschränkt": "#e08214", "unzureichend": "#b2182b"}
    ref = np.array([f.hf_ref_ekg for f in fenster])
    ppg = np.array([f.hf_ppg for f in fenster])
    q = np.array([f.qualitaet for f in fenster])
    k = kennzahlen(ppg[q == "gut"], ref[q == "gut"])
    pfade = []

    fig, ax = plt.subplots(figsize=(5.5, 5))
    for name, farbe in farben.items():
        m = q == name
        ax.scatter(ref[m], ppg[m], s=12, alpha=0.6, color=farbe, label=f"{name} (n={m.sum()})")
    grenzen = [np.nanmin([ref.min(), ppg.min()]) - 5, np.nanmax([ref.max(), ppg.max()]) + 5]
    ax.plot(grenzen, grenzen, "k--", lw=1, label="Identität")
    ax.set_xlabel("Referenz: Herzfrequenz Monitor (EKG) [/min]")
    ax.set_ylabel("Schätzung aus PPG [/min]")
    ax.set_title("Pulsanalyse vs. Monitor (BIDMC, 30-s-Fenster)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    p = aus / "vergleich_streudiagramm.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    pfade.append(p)

    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    mittel, diff = (ppg + ref) / 2, ppg - ref
    for name, farbe in farben.items():
        m = q == name
        ax.scatter(mittel[m], diff[m], s=12, alpha=0.6, color=farbe, label=name)
    for y, stil, text in ((k.bias, "-", "Bias"), (k.loa_unten, "--", "−1,96 SD"), (k.loa_oben, "--", "+1,96 SD")):
        ax.axhline(y, color="#1b7837", ls=stil, lw=1)
        ax.text(ax.get_xlim()[1], y, f" {text}: {y:+.1f}".replace(".", ","), va="center", fontsize=8)
    ax.set_xlabel("Mittelwert beider Methoden [/min]")
    ax.set_ylabel("Differenz PPG − Referenz [/min]")
    ax.set_title("Bland-Altman (Linien: Fenster mit Qualität „gut“)")
    ax.legend(fontsize=8, loc="lower left")
    fig.tight_layout()
    p = aus / "bland_altman.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    pfade.append(p)
    return pfade


def bericht(z: dict[str, Kennzahlen], n_aufnahmen: int, fenster_s: float) -> str:
    def f(x, nk=1):
        return "–" if not np.isfinite(x) else f"{x:.{nk}f}".replace(".", ",")

    zeilen = [
        f"Validierung mit {n_aufnahmen} Aufnahmen, Fensterlänge {fenster_s:.0f} s, Referenz: Herzfrequenz des Monitors (EKG).",
        "",
        "| Qualität | Fenster | MAE [/min] | RMSE [/min] | Bias [/min] | 95-%-Grenzen [/min] | Anteil ±5 /min |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, k in z.items():
        zeilen.append(
            f"| {name} | {k.n} | {f(k.mae)} | {f(k.rmse)} | {f(k.bias)} | "
            f"{f(k.loa_unten)} bis {f(k.loa_oben)} | {f(k.anteil_5 * 100, 0)} % |"
        )
    return "\n".join(zeilen)


def validiere(ordner: str | Path, aus: str | Path, fenster_s: float = 30.0) -> tuple[str, list[Fenster]]:
    aufnahmen = finde_aufnahmen(ordner)
    if not aufnahmen:
        raise FileNotFoundError(f"Keine bidmc_XX_Signals.csv/Numerics.csv unter {ordner} gefunden.")
    alle: list[Fenster] = []
    for nr, sig, num in aufnahmen:
        alle.extend(werte_aufnahme_aus(nr, sig, num, fenster_s))
    aus = Path(aus)
    aus.mkdir(parents=True, exist_ok=True)
    schreibe_csv(alle, aus / "validierung_fenster.csv")
    diagramme(alle, aus)
    text = bericht(zusammenfassung(alle), len(aufnahmen), fenster_s)
    (aus / "validierung_bericht.md").write_text(text + "\n", encoding="utf-8")
    return text, alle
