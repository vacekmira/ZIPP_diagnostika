import io
import re
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib.pagesizes import A0, A1, A2, A3, A4, landscape

from app import APP_VERSION
from app.export_options import FONT_SIZES, PAPER_SIZES, ExportOptions
from app.plan_pdf import resolve_plan_pdf_layout


ROOT = Path(__file__).resolve().parents[1]


def create_project(client, *, bays=3, trusses=24, name="Hala Žďár – zkouška"):
    response = client.post("/api/projects", json={
        "name": name,
        "bay_count": bays,
        "default_truss_count": trusses,
        "note": "Příliš žluťoučký kůň úpěl ďábelské ódy. Kôň, ľalia a ŕieka.",
        "technician_name": "Alpha 8 tester",
    })
    assert response.status_code == 201, response.text
    return response.json()


def pdf_reader(response) -> PdfReader:
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"%PDF")
    return PdfReader(io.BytesIO(response.content))


def assert_version_is_footer_only(reader: PdfReader) -> None:
    for page in reader.pages:
        text = page.extract_text() or ""
        assert text.count(APP_VERSION) == 1
        assert f"Půdorys objektu - {APP_VERSION}" not in text
        assert f"Pôdorys objektu - {APP_VERSION}" not in text
        assert f"verze {APP_VERSION}" not in text
        assert f"verzia {APP_VERSION}" not in text
    metadata_text = " ".join(str(value) for value in (reader.metadata or {}).values())
    assert APP_VERSION not in metadata_text


def add_reference_states(client, project):
    bay = project["bays"][0]
    trusses = bay["trusses"]
    assert client.patch(f"/api/trusses/{trusses[0]['id']}/type", json={
        "type": "gable", "technician_name": "Alpha 8 tester", "expected_version": trusses[0]["version"],
    }).status_code == 200
    assert client.post(f"/api/bays/{bay['id']}/dilation-pairs", json={
        "technician_name": "Alpha 8 tester",
        "truss_a_id": trusses[4]["id"],
        "truss_b_id": trusses[5]["id"],
        "expected_version_a": trusses[4]["version"],
        "expected_version_b": trusses[5]["version"],
    }).status_code == 201
    assert client.put(f"/api/trusses/{trusses[2]['id']}/diagnostics/left", json={
        "done": True, "technician_name": "Alpha 8 tester", "expected_version": trusses[2]["version"],
    }).status_code == 200
    assert client.post(f"/api/trusses/{trusses[3]['id']}/exclude", json={
        "reason": "leak", "note": "Zatečení u Žďáru.", "technician_name": "Alpha 8 tester",
        "expected_version": trusses[3]["version"],
    }).status_code == 200


def test_current_release_assets_font_and_deployment_are_alpha8(client):
    assert APP_VERSION == "Alpha 8"
    assert client.get("/health").json()["version"] == "Alpha 8"
    assert 'version = "0.8.0a8"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "zipp-diagnostics:alpha8" in (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "fonts-dejavu-core" not in (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert not (ROOT / "app/static/alpha4.css").exists()
    assert (ROOT / "app/static/alpha8.css").is_file()
    assert (ROOT / "app/assets/fonts/DejaVuSans.ttf").stat().st_size > 500_000
    assert (ROOT / "app/assets/fonts/DejaVuSans-Bold.ttf").stat().st_size > 500_000
    assert (ROOT / "app/assets/fonts/LICENSE-DejaVu.txt").is_file()
    page = client.get("/").text
    assert "/static/app.js?v=alpha-8" in page
    assert "/static/alpha8.css?v=alpha-8" in page
    script = client.get("/static/app.js?v=alpha-8").text
    assert 'const scriptVersion = "Alpha 8"' in script
    assert "downloadPdf" in script and "zipp.exportOptions" in script


def test_bay_and_project_use_the_same_export_options_dialog(client):
    project = create_project(client, bays=1, trusses=10)
    pages = (
        client.get(f"/projects/{project['id']}/plan").text,
        client.get(f"/bays/{project['bays'][0]['id']}").text,
    )
    expected = ["A4", "A3", "A2", "A1", "A0", "landscape", "portrait", "auto", "7", "9", "10", "12", "14"]
    for page in pages:
        assert "data-export-dialog" in page and "data-export-form" in page
        assert re.findall(r'<option value="([^"]+)"', page) == expected
        assert '<option value="A3" selected>' in page
        assert '<option value="landscape" selected>' in page
        assert '<option value="auto" selected>' in page
    script = client.get("/static/app.js").text
    assert script.count("$$('[data-export-form]')") == 1
    assert "zipp.exportOptions" in script


def test_shared_export_options_validate_and_size_pages():
    options = ExportOptions("A2", "portrait", "14")
    assert options.page_dimensions == A2
    assert options.requested_font_size == 14
    assert ExportOptions("a3", "LANDSCAPE", "large").font_size == "14"


def test_every_iso_page_honors_orientation_and_is_exactly_one_page(client):
    project = create_project(client, bays=1, trusses=10, name="Malá hala Žďár")
    expected = {"A4": A4, "A3": A3, "A2": A2, "A1": A1, "A0": A0}
    for paper, portrait in expected.items():
        reader = pdf_reader(client.get(
            f"/api/projects/{project['id']}/plan.pdf?page_size={paper}&font_size=auto&lang=cs"
        ))
        assert len(reader.pages) == 1
        width, height = landscape(portrait)
        box = reader.pages[0].mediabox
        assert abs(float(box.width) - width) < 0.1
        assert abs(float(box.height) - height) < 0.1
        assert float(box.width) > float(box.height)
        portrait_reader = pdf_reader(client.get(
            f"/api/projects/{project['id']}/plan.pdf?page_size={paper}&orientation=portrait&font_size=auto&lang=cs"
        ))
        assert len(portrait_reader.pages) == 1
        portrait_box = portrait_reader.pages[0].mediabox
        assert abs(float(portrait_box.width) - portrait[0]) < 0.1
        assert abs(float(portrait_box.height) - portrait[1]) < 0.1
        assert float(portrait_box.height) > float(portrait_box.width)


def test_full_project_matrix_is_one_page_unicode_and_keeps_requested_font(client):
    project = create_project(client)
    add_reference_states(client, project)
    project = client.get(f"/api/projects/{project['id']}").json()
    matrix = (("A4", "landscape", "auto"), ("A3", "landscape", "10"), ("A2", "portrait", "14"), ("A1", "landscape", "14"))
    for paper, orientation, size in matrix:
        response = client.get(
            f"/api/projects/{project['id']}/plan.pdf?page_size={paper}&orientation={orientation}&font_size={size}&lang=cs"
        )
        reader = pdf_reader(response)
        assert len(reader.pages) == 1
        text = reader.pages[0].extract_text()
        assert "■" not in text
        assert "Půdorys objektu" in text
        assert "Loď A" in text
        assert "Běžný" in text
        assert "Dilatační" in text
        assert "Hala Žďár – zkouška" in text
        assert_version_is_footer_only(reader)
    layout = resolve_plan_pdf_layout(project, "cs", page_size="A2", font_size="12")
    assert layout.font_size == 12
    explicit = client.get(f"/api/projects/{project['id']}/plan.pdf?page_size=A2&font_size=12")
    content = PdfReader(io.BytesIO(explicit.content)).pages[0].get_contents().get_data()
    assert re.search(rb"\b12(?:\.0+)? Tf\b", content)


def test_invalid_combination_is_rejected_with_useful_recommendation(client):
    project = create_project(client, bays=3, trusses=100, name="Velká hala")
    response = client.get(f"/api/projects/{project['id']}/plan.pdf?page_size=A4&font_size=14")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "A4 / Landscape / 14 pt" in detail["message"]
    assert detail["recommendations"]
    assert any(
        "A" in item or "pt" in item or "větší" in item or "menší" in item
        for item in detail["recommendations"]
    )


def test_small_medium_and_large_halls_never_split(client):
    cases = ((1, 10, "A4"), (3, 24, "A3"), (5, 60, "A0"))
    for bays, trusses, paper in cases:
        project = create_project(client, bays=bays, trusses=trusses, name=f"Hala {bays}x{trusses}")
        reader = pdf_reader(client.get(
            f"/api/projects/{project['id']}/plan.pdf?page_size={paper}&font_size=auto"
        ))
        assert len(reader.pages) == 1
        text = reader.pages[0].extract_text()
        assert "1/1" in text
        assert not re.search(r"\b1-18\b|\b19-", text)


def test_bay_pdf_physical_sizes_use_embedded_unicode_font_without_black_squares(client):
    project = create_project(client, bays=1, trusses=10, name="Žďár – česká a slovenská zkouška")
    add_reference_states(client, project)
    byte_lengths = []
    cases = (
        ("A4", "landscape", "7", landscape(A4)),
        ("A2", "portrait", "14", A2),
    )
    for paper, orientation, size, expected_page in cases:
        response = client.get(
            f"/api/bays/{project['bays'][0]['id']}/report.pdf?"
            f"page_size={paper}&orientation={orientation}&font_size={size}&lang=sk"
        )
        reader = pdf_reader(response)
        assert response.headers["x-zipp-page-size"] == paper
        assert response.headers["x-zipp-orientation"] == orientation
        for page in reader.pages:
            assert abs(float(page.mediabox.width) - expected_page[0]) < 0.1
            assert abs(float(page.mediabox.height) - expected_page[1]) < 0.1
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        assert "■" not in text
        assert "Pôdorys objektu" in text
        assert "Loď A" in text
        assert "Bežný" in text
        assert "Dilatačný" in text
        fonts = []
        for page in reader.pages:
            for reference in page["/Resources"].get("/Font", {}).values():
                fonts.append(str(reference.get_object().get("/BaseFont")))
        assert any("DejaVuSans" in font for font in fonts)
        assert_version_is_footer_only(reader)
        byte_lengths.append(len(response.content))
    assert byte_lengths[0] != byte_lengths[1]


def test_pdf_fonts_cover_complete_czech_slovak_latin_extended_sample(client):
    glyphs = "áäčďéěíĺľňóôŕřšťúůýž ÁÄČĎÉĚÍĹĽŇÓÔŔŘŠŤÚŮÝŽ"
    project = create_project(client, bays=1, trusses=2, name=f"Hala {glyphs}")
    full = pdf_reader(client.get(
        f"/api/projects/{project['id']}/plan.pdf?page_size=A2&orientation=landscape&font_size=10&lang=cs"
    ))
    full_text = "\n".join(page.extract_text() or "" for page in full.pages)
    assert glyphs in full_text
    assert "■" not in full_text
    bay = pdf_reader(client.get(
        f"/api/bays/{project['bays'][0]['id']}/report.pdf?font_size=14&lang=sk"
    ))
    bay_text = "\n".join(page.extract_text() or "" for page in bay.pages)
    assert glyphs in bay_text
    assert "■" not in bay_text


def test_rename_is_reflected_in_fresh_full_pdf_and_keeps_project_id(client):
    project = create_project(client, bays=1, trusses=10, name="Původní hala")
    response = client.patch(f"/api/projects/{project['id']}/name", json={
        "name": "Hala Žďár – zkouška", "technician_name": "Alpha 8 tester",
    })
    assert response.status_code == 200
    assert response.json()["id"] == project["id"]
    reader = pdf_reader(client.get(f"/api/projects/{project['id']}/plan.pdf?page_size=A3&font_size=10"))
    text = reader.pages[0].extract_text()
    assert "Hala Žďár – zkouška" in text
    assert "Původní hala" not in text
    assert reader.metadata.subject == "Půdorys objektu"
    assert_version_is_footer_only(reader)
