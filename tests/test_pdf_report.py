import unittest
from utils.pdf_report import FinTwinPDFReport, _clean_text_for_pdf

class TestPDFReport(unittest.TestCase):
    def test_clean_text_with_font_awesome(self):
        text = '<i class="fa-solid fa-arrow-trend-down" style="color:#EF4444; margin-right:4px;"></i> <b>Savings Rate</b> \u2014 your savings rate of 0.0% reduced your score by <b>+12.5 pts</b>.'
        cleaned = _clean_text_for_pdf(text)
        self.assertNotIn('<i class=', cleaned)
        self.assertNotIn('</i>', cleaned)
        self.assertIn('<b>Savings Rate</b>', cleaned)
        self.assertIn('(-) ', cleaned)

    def test_pdf_build_with_icon_paragraphs(self):
        rep = FinTwinPDFReport(report_title="Test Report", user_id="test_user")
        rep.add_paragraph('<i class="fa-solid fa-arrow-trend-up" style="color:#10B981;"></i> <b>Income Growth</b> increased score.')
        rep.add_paragraph('<i class="fa-solid fa-arrow-trend-down" style="color:#EF4444;"></i> <b>High EMI</b> decreased score.')
        rep.add_paragraph('<span style="color:#EF4444;">Critical alert</span> text.')
        pdf_bytes = rep.build()
        self.assertTrue(len(pdf_bytes) > 1000)

if __name__ == '__main__':
    unittest.main()
