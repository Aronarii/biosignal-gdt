import tempfile
import unittest
from pathlib import Path

import numpy as np

from biosignal_gdt.signal import synthetisches_ppg
from biosignal_gdt.validierung import finde_aufnahmen, kennzahlen, validiere


def bidmc_attrappe(ordner: Path, nr: str, hf: float, dauer_s: int = 120) -> None:
    """Schreibt Dateien im BIDMC-CSV-Format (künstliches Signal, keine echten Daten)."""
    fs = 125
    ppg = synthetisches_ppg(fs=fs, dauer_s=dauer_s, hf=hf, seed=int(hf))
    with open(ordner / f"bidmc_{nr}_Signals.csv", "w") as f:
        f.write("Time [s], RESP, PLETH, V, AVR, II\n")
        for i, x in enumerate(ppg):
            f.write(f"{i / fs:.3f},0.5,{x:.5f},0.1,0.2,0.3\n")
    with open(ordner / f"bidmc_{nr}_Numerics.csv", "w") as f:
        f.write("Time [s], HR, PULSE, RESP, SpO2\n")
        for t in range(dauer_s):
            hr = "" if t == 5 else f"{hf:.0f}"  # eine Lücke wie in echten Daten
            f.write(f"{t},{hr},{hf:.0f},15,98\n")


class TestKennzahlen(unittest.TestCase):
    def test_bekannte_werte(self):
        k = kennzahlen([62, 70, 81, 90], [60, 70, 80, 90])  # Differenzen 2, 0, 1, 0
        self.assertEqual(k.n, 4)
        self.assertAlmostEqual(k.mae, 0.75)
        self.assertAlmostEqual(k.bias, 0.75)
        self.assertAlmostEqual(k.rmse, np.sqrt(5 / 4))
        sd = np.std([2, 0, 1, 0], ddof=1)
        self.assertAlmostEqual(k.loa_oben, 0.75 + 1.96 * sd)
        self.assertAlmostEqual(k.anteil_5, 1.0)

    def test_nan_wird_ignoriert(self):
        k = kennzahlen([60, np.nan, 80], [60, 70, np.nan])
        self.assertEqual(k.n, 1)
        self.assertEqual(k.mae, 0)


class TestValidierungsablauf(unittest.TestCase):
    def test_ablauf_mit_attrappe(self):
        with tempfile.TemporaryDirectory() as tmp:
            daten, aus = Path(tmp) / "bidmc_csv", Path(tmp) / "aus"
            daten.mkdir()
            bidmc_attrappe(daten, "01", 60)
            bidmc_attrappe(daten, "02", 95)
            self.assertEqual(len(finde_aufnahmen(daten)), 2)
            text, fenster = validiere(daten, aus)
            self.assertEqual(len(fenster), 8)  # 2 Aufnahmen x 4 Fenster à 30 s
            for f in fenster:
                self.assertAlmostEqual(f.hf_ppg, f.hf_ref_ekg, delta=3)
            for name in ("validierung_fenster.csv", "validierung_bericht.md",
                         "vergleich_streudiagramm.png", "bland_altman.png"):
                self.assertTrue((aus / name).exists(), name)
            self.assertIn("| gut |", text)


if __name__ == "__main__":
    unittest.main()
