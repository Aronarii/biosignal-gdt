import unittest
from datetime import datetime

import numpy as np

from biosignal_gdt.gdt import GdtRecord, validate
from biosignal_gdt.signal import auswerten, synthetisches_ppg
from biosignal_gdt.workflow import antwort_6310
from tests.test_gdt import beispiel


class TestAuswertung(unittest.TestCase):
    def test_herzfrequenz_wird_getroffen(self):
        for hf in (40, 55, 72, 110, 150):
            e = auswerten(synthetisches_ppg(hf=hf, seed=hf), fs=125)
            self.assertAlmostEqual(e.hf_mittel, hf, delta=3, msg=f"HF {hf}")
            self.assertEqual(e.qualitaet, "gut")

    def test_niedrige_hf_keine_doppelzaehlung(self):
        # Bei 35-45 /min liegt die dikrote Welle weit vom Hauptgipfel und darf
        # nicht als eigener Schlag gezählt werden (Fehler aus einem frühen Test).
        for hf in (35, 40, 45):
            for seed in (1, 2, 3):
                e = auswerten(synthetisches_ppg(hf=hf, seed=seed * hf), fs=125)
                self.assertAlmostEqual(e.hf_mittel, hf, delta=2, msg=f"HF {hf}, seed {seed}")

    def test_rauschen_senkt_qualitaet(self):
        rng = np.random.default_rng(0)
        e = auswerten(rng.standard_normal(125 * 60), fs=125)
        self.assertNotEqual(e.qualitaet, "gut")

    def test_zu_kurzes_signal(self):
        with self.assertRaises(ValueError):
            auswerten(np.zeros(100), fs=125)


class TestWorkflow(unittest.TestCase):
    def test_antwort_ist_gueltig_und_uebernimmt_patient(self):
        anforderung = GdtRecord.from_bytes(beispiel().to_bytes())
        e = auswerten(synthetisches_ppg(hf=72), fs=125)
        antwort = antwort_6310(anforderung, e, datetime(2026, 10, 20, 15, 30))
        data = antwort.to_bytes()
        self.assertEqual(validate(data), [])
        rec = GdtRecord.from_bytes(data)
        self.assertEqual(rec.satzart, "6310")
        self.assertEqual(rec.get("3000"), "4711")
        self.assertEqual(rec.get("8315"), "PRAXIS01")  # zurück an die Praxissoftware
        self.assertEqual(rec.get("6200"), "20102026")
        self.assertIn("HF", rec.get_all("8410"))


if __name__ == "__main__":
    unittest.main()
