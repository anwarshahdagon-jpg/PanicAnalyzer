import os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
from analyzer import Analyzer, NotAPanicLog, parse_file

S = lambda n: os.path.join(ROOT, "samples", n)

class T(unittest.TestCase):
    a = Analyzer()
    def top(self, name):
        return self.a.analyze(parse_file(S(name)))
    def test_prs0(self):
        f = self.top("panic-full-2026-11-15-102144.000.ips")
        self.assertIn("PRS0", f[0].title); self.assertEqual(f[0].confidence, "High")
        self.assertIn("charging port flex", f[0].why.lower())
    def test_no_extension_multi_sensor(self):
        titles = " ".join(x.title for x in self.top("panic-no-ext"))
        self.assertIn("MIC1", titles); self.assertIn("TG0B", titles)
    def test_i2c_txt(self):
        f = self.top("i2c-panic.txt"); self.assertIn("I2C bus 0", f[0].component)
    def test_reject_text(self):
        with self.assertRaises(NotAPanicLog): parse_file(S("not-a-panic.txt"))
    def test_reject_app_crash(self):
        with self.assertRaises(NotAPanicLog): parse_file(S("app-crash.ips"))

if __name__ == "__main__":
    unittest.main()
