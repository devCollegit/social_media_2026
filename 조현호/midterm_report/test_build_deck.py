import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader

from build_deck import BLUE, TOTAL_PAGES, WHITE, Deck, build_deck, contrast_ratio


class DeckLayoutTests(unittest.TestCase):
    def test_complete_deck_has_nine_pages_and_embedded_fonts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "deck.pdf"
            deck = build_deck(output)
            reader = PdfReader(output)
            self.assertEqual(len(reader.pages), TOTAL_PAGES)
            self.assertEqual(len(deck.page_regions), TOTAL_PAGES)
            for page in reader.pages:
                self.assertEqual(tuple(page.mediabox), (0, 0, 960, 540))
                self.assertTrue(page.extract_text().strip())
                for font in page["/Resources"]["/Font"].values():
                    font = font.get_object()
                    if font["/Subtype"] == "/TrueType":
                        self.assertIn("/FontFile2", font["/FontDescriptor"])
            content = "".join(page.extract_text() for page in reader.pages)
            for expected in ("다섯 하위 지표", "H1", "가정 A", "13명", "실증 수치는 없으며", "KRX 지표 정의", "합성입니다"):
                self.assertIn(expected, content)

    def test_overlapping_paragraphs_are_rejected(self):
        deck = Deck()
        deck.paragraph(42, 364, 200, "첫 문장")
        with self.assertRaisesRegex(ValueError, "overlapping text"):
            deck.paragraph(42, 364, 200, "겹치는 문장")

    def test_overflow_and_small_body_text_are_rejected(self):
        deck = Deck()
        with self.assertRaisesRegex(ValueError, "exceeds its area"):
            deck.paragraph(42, 60, 200, "한 줄<br/>다음 줄")
        with self.assertRaisesRegex(ValueError, "too small"):
            deck.paragraph(42, 364, 200, "작은 본문", size=9)

    def test_background_cannot_hide_previously_drawn_text(self):
        deck = Deck()
        deck.paragraph(56, 350, 200, "이미 그린 글자")
        with self.assertRaisesRegex(ValueError, "obscures text"):
            deck.box(42, 364, 300, 100)

    def test_text_cannot_cross_its_background(self):
        deck = Deck()
        deck.box(42, 364, 200, 50)
        with self.assertRaisesRegex(ValueError, "spills out"):
            deck.paragraph(56, 350, 170, "첫 줄<br/>둘째 줄<br/>셋째 줄")

    def test_missing_glyphs_and_invisible_text_are_rejected(self):
        deck = Deck()
        with self.assertRaisesRegex(ValueError, "Unsupported glyphs"):
            deck.paragraph(42, 364, 200, "지원하지 않는 글자 \U0010ffff")
        with self.assertRaisesRegex(ValueError, "contrast"):
            deck.paragraph(42, 364, 200, "흰 배경의 흰 글자", color=WHITE)
        self.assertGreaterEqual(contrast_ratio(WHITE, BLUE), 4.5)

    def test_table_rows_expand_to_fit_long_cells(self):
        deck = Deck()
        short = deck.table(42, 364, [200, 200], ["항목", "설명"], [["짧음", "설명"]])
        deck = Deck()
        long = deck.table(42, 364, [200, 200], ["항목", "설명"],
                          [["긴 내용", "줄바꿈과 행 높이를 점검하는 긴 설명입니다. " * 5]])
        self.assertLess(long, short)


if __name__ == "__main__":
    unittest.main()
