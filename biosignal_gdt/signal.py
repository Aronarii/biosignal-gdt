"""Auswertung eines Pulssignals (PPG) oder EKG: Schläge erkennen, Herzfrequenz und HRV.

Bewusst einfache, nachvollziehbare Verfahren statt Black Box:
Bandpassfilter -> Spitzenerkennung -> RR-Intervalle -> Kennzahlen + Plausibilitätsprüfung.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass

import numpy as np
from scipy.signal import butter, filtfilt, find_peaks

RR_MIN_S = 0.3   # entspricht 200 /min
RR_MAX_S = 2.0   # entspricht 30 /min


@dataclass
class Ergebnis:
    fs: float
    dauer_s: float
    n_schlaege: int
    hf_mittel: float      # Schläge pro Minute
    hf_min: float
    hf_max: float
    sdnn_ms: float        # Standardabweichung der RR-Intervalle
    rmssd_ms: float       # Wurzel aus dem mittleren Quadrat aufeinanderfolgender Differenzen
    anteil_plausibel: float  # Anteil der RR-Intervalle im plausiblen Bereich (0..1)
    peaks: np.ndarray
    gefiltert: np.ndarray

    @property
    def qualitaet(self) -> str:
        if self.n_schlaege < 10 or self.anteil_plausibel < 0.8:
            return "unzureichend"
        if self.anteil_plausibel < 0.95:
            return "eingeschränkt"
        return "gut"


def synthetisches_ppg(fs: float = 125.0, dauer_s: float = 60.0, hf: float = 72.0,
                      variabilitaet: float = 0.04, rauschen: float = 0.05, seed: int = 1) -> np.ndarray:
    """Erzeugt ein künstliches Pulssignal zum Testen (keine echten Patientendaten)."""
    rng = np.random.default_rng(seed)
    t = np.arange(0, dauer_s, 1 / fs)
    sig = np.zeros_like(t)
    beat = 0.0
    rr_mittel = 60.0 / hf
    while beat < dauer_s:
        # Pulswelle: systolischer Gipfel + kleinere dikrote Welle
        sig += np.exp(-((t - beat - 0.15) ** 2) / (2 * 0.05 ** 2))
        sig += 0.35 * np.exp(-((t - beat - 0.40) ** 2) / (2 * 0.07 ** 2))
        beat += rr_mittel * (1 + variabilitaet * rng.standard_normal())
    sig += 0.3 * np.sin(2 * np.pi * 0.25 * t)          # Atmung / Baseline-Drift
    sig += rauschen * rng.standard_normal(t.size)       # Messrauschen
    return sig


def lade_csv(pfad: str, spalte: str) -> np.ndarray:
    """Liest eine Signalspalte aus einer CSV-Datei (z. B. BIDMC-Export: Spalte 'PLETH')."""
    werte = []
    with open(pfad, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        name = next((n for n in reader.fieldnames or [] if n.strip().upper() == spalte.upper()), None)
        if name is None:
            raise KeyError(f"Spalte {spalte!r} nicht gefunden. Vorhanden: {reader.fieldnames}")
        for zeile in reader:
            try:
                werte.append(float(zeile[name]))
            except (TypeError, ValueError):
                continue
    return np.asarray(werte)


def bandpass(sig: np.ndarray, fs: float, low: float = 0.5, high: float = 8.0) -> np.ndarray:
    b, a = butter(3, [low / (fs / 2), high / (fs / 2)], btype="band")
    return filtfilt(b, a, sig)


def grundperiode_s(gefiltert: np.ndarray, fs: float) -> float | None:
    """Schätzt den mittleren Schlagabstand über die Autokorrelation.

    Hintergrund: Die Pulswelle hat neben dem Hauptgipfel eine kleinere dikrote Welle.
    Bei niedriger Herzfrequenz liegt sie weit genug vom Hauptgipfel entfernt, dass eine
    reine Spitzensuche sie als eigenen Schlag zählen kann. Die Autokorrelation ist am
    größten bei der echten Periode und hilft, den Mindestabstand passend zu wählen.
    """
    x = gefiltert - gefiltert.mean()
    ac = np.correlate(x, x, mode="full")[x.size - 1:]
    ac /= ac[0]
    lo, hi = int(RR_MIN_S * fs), min(int(RR_MAX_S * fs), ac.size - 1)
    kandidaten, eig = find_peaks(ac[lo:hi], height=0.3)
    if kandidaten.size == 0:
        return None
    # erster deutlicher Gipfel, der mindestens 80 % des höchsten erreicht
    hoehen = eig["peak_heights"]
    erster = kandidaten[np.argmax(hoehen >= 0.8 * hoehen.max())]
    return (erster + lo) / fs


def auswerten(sig: np.ndarray, fs: float) -> Ergebnis:
    if sig.size < fs * 10:
        raise ValueError("Signal zu kurz: mindestens 10 Sekunden nötig.")
    gefiltert = bandpass(np.asarray(sig, dtype=float), fs)
    periode = grundperiode_s(gefiltert, fs)
    mindestabstand = 0.6 * periode if periode else RR_MIN_S
    peaks, _ = find_peaks(
        gefiltert,
        distance=max(1, int(mindestabstand * fs)),
        prominence=0.3 * np.std(gefiltert),
    )
    rr = np.diff(peaks) / fs
    plausibel = (rr >= RR_MIN_S) & (rr <= RR_MAX_S)
    rr_ok = rr[plausibel] if plausibel.any() else rr
    hf = 60.0 / rr_ok if rr_ok.size else np.array([np.nan])
    # RMSSD nur aus Paaren aufeinanderfolgender, beide plausibler Intervalle
    paare = plausibel[:-1] & plausibel[1:]
    diffs = np.diff(rr)[paare]
    # Gegenprobe: Spitzenzählung und Autokorrelation müssen zusammenpassen
    if periode and rr_ok.size and abs(rr_ok.mean() - periode) / periode > 0.15:
        plausibel = np.zeros_like(plausibel)  # Widerspruch -> Qualität unzureichend
    return Ergebnis(
        fs=fs,
        dauer_s=sig.size / fs,
        n_schlaege=int(peaks.size),
        hf_mittel=float(60.0 / rr_ok.mean()) if rr_ok.size else float("nan"),
        hf_min=float(np.min(hf)),
        hf_max=float(np.max(hf)),
        sdnn_ms=float(np.std(rr_ok, ddof=1) * 1000) if rr_ok.size > 1 else float("nan"),
        rmssd_ms=float(np.sqrt(np.mean(diffs ** 2)) * 1000) if diffs.size else float("nan"),
        anteil_plausibel=float(plausibel.mean()) if rr.size else 0.0,
        peaks=peaks,
        gefiltert=gefiltert,
    )
