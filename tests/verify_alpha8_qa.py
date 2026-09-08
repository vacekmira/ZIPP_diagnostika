"""Check actual PDFs downloaded by browser_alpha8.mjs (render separately)."""
import json
import math
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib.pagesizes import A2, A3, A4, landscape


ROOT = Path(__file__).resolve().parents[1]
CASES = (
    ('bay-clean', landscape(A4), False, 7),
    ('bay-access', landscape(A3), True, 10),
    ('bay-A2-access', A2, True, 14),
    ('plan-clean', landscape(A4), False, None),
    ('plan-access', landscape(A3), True, 10),
    ('plan-A2-access', A2, True, 14),
)


def main():
    results = []
    for name, dimensions, show_access, font_size in CASES:
        path = ROOT / 'tmp' / 'browser-alpha8' / f'alpha8-browser-{name}.pdf'
        reader = PdfReader(path)
        if name.startswith('plan'):
            assert len(reader.pages) == 1, name
        all_text = ''
        label_sizes = []
        for page in reader.pages:
            assert abs(float(page.mediabox.width) - dimensions[0]) < 0.1, name
            assert abs(float(page.mediabox.height) - dimensions[1]) < 0.1, name
            footer_y = []

            def visit(text, cm, tm, font, size):
                if 'Alpha 8' in text:
                    footer_y.append(tm[4] * cm[1] + tm[5] * cm[3] + cm[5])
                if text.strip() == 'A1' and abs(cm[1]) > 0.01:
                    label_sizes.append(size * math.hypot(cm[2], cm[3]))

            text = page.extract_text(visitor_text=visit)
            assert text.count('Alpha 8') == 1, name
            assert len(footer_y) == 1 and 0 <= footer_y[0] < 35, (name, footer_y)
            assert not any(char in text for char in ('■', '\ufffd', '\x00')), name
            all_text += '\n' + text
        assert 'Alpha 8' not in str(reader.metadata), name
        assert 'Hala Žďár – zkouška' in all_text, name
        assert 'Běžný' in all_text and 'Dilatační' in all_text, name
        assert ('Přístupy - legenda' in all_text) == show_access, name
        assert ('Výška: 12,25 m' in all_text) == show_access, name
        if show_access:
            for label in ('N = Nůžková plošina', 'K = Kloubová plošina', 'Ž = Žebřík', 'L = Lezecká technika', 'J = Jeřábová dráha'):
                assert label in all_text, (name, label)
            if name.startswith('plan'):
                assert 'Výška: 8,5 m' in all_text, name
        if name.startswith('bay'):
            assert ('kôň, ľalia.' in all_text) == show_access, name
        if font_size is not None:
            assert len(label_sizes) == 1, (name, label_sizes)
            assert abs(label_sizes[0] - font_size) < 0.02, (name, label_sizes)
        results.append({'file': path.name, 'pages': len(reader.pages), 'size_pt': list(dimensions), 'access': show_access, 'label_pt': label_sizes})
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
