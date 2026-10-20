import unittest

from biosignal_gdt.gdt import GdtRecord, validate


def beispiel() -> GdtRecord:
    r = GdtRecord()
    r.add("8000", "6302").add("8315", "BSGDT01").add("8316", "PRAXIS01")
    r.add("9206", "3").add("9218", "02.10").add("3000", "4711")
    r.add("3101", "Müller").add("3102", "Jörg").add("3103", "21011980")
    return r


class TestZeilen(unittest.TestCase):
    def test_bekannte_zeile(self):
        # Bekanntes Beispiel aus der Praxis: "01380006302" = Satzart 6302
        self.assertEqual(GdtRecord()._encode_line("8000", "6302"), b"01380006302\r\n")

    def test_umlaut_zaehlt_in_ansi_ein_byte(self):
        self.assertEqual(GdtRecord()._encode_line("3101", "Müller")[:3], b"015")


class TestSatz(unittest.TestCase):
    def test_satzlaenge_stimmt(self):
        data = beispiel().to_bytes()
        rec = GdtRecord.from_bytes(data)
        self.assertEqual(int(rec.get("8100")), len(data))

    def test_8100_steht_an_zweiter_stelle(self):
        rec = GdtRecord.from_bytes(beispiel().to_bytes())
        self.assertEqual([k for k, _ in rec.fields[:2]], ["8000", "8100"])

    def test_ohne_9206_gilt_cp437(self):
        r = GdtRecord(encoding="cp437").add("8000", "6302").add("3000", "1").add("3101", "Müller")
        self.assertEqual(GdtRecord.from_bytes(r.to_bytes()).get("3101"), "Müller")

    def test_rundreise(self):
        rec = GdtRecord.from_bytes(beispiel().to_bytes())
        self.assertEqual(rec.get("3101"), "Müller")
        self.assertEqual(rec.get("3102"), "Jörg")

    def test_gueltiger_satz_hat_keine_probleme(self):
        self.assertEqual(validate(beispiel().to_bytes()), [])


class TestValidierung(unittest.TestCase):
    def test_falsche_zeilenlaenge(self):
        data = beispiel().to_bytes().replace(b"0133000", b"0143000")
        self.assertTrue(any("Länge" in p for p in validate(data)))

    def test_falsche_satzlaenge(self):
        data = beispiel().to_bytes() + GdtRecord()._encode_line("6227", "extra")
        self.assertTrue(any("Satzlänge" in p for p in validate(data)))

    def test_pflichtfeld_fehlt(self):
        r = GdtRecord().add("8000", "6302").add("3101", "Test")
        self.assertTrue(any("3000" in p for p in validate(r.to_bytes())))

    def test_geburtsdatum_format(self):
        r = beispiel()
        r.fields = [(k, "1980-01-21" if k == "3103" else v) for k, v in r.fields]
        self.assertTrue(any("TTMMJJJJ" in p for p in validate(r.to_bytes())))


if __name__ == "__main__":
    unittest.main()
