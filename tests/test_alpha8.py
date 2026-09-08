import io
import math
from pypdf import PdfReader
from sqlalchemy import select

from app import APP_VERSION
from app.models import AuditLog


def test_bay_diagram_keeps_physical_point_size_with_and_without_access(client):
    project = create(client)
    bay = project['bays'][0]
    for enabled in (False, True):
        for paper, orientation, size in (('A4', 'landscape', 7), ('A3', 'landscape', 10), ('A2', 'portrait', 14)):
            response = client.get(
                f'/api/bays/{bay["id"]}/report.pdf?page_size={paper}&orientation={orientation}'
                f'&font_size={size}&show_access={str(enabled).lower()}'
            )
            assert response.status_code == 200, response.text
            sizes = []

            def visit(text, cm, tm, font, font_size):
                # Rotated A1 is the label inside the schematic, not the table.
                if text.strip() == 'A1' and abs(cm[1]) > 0.01:
                    sizes.append(font_size * math.hypot(cm[2], cm[3]))

            for page in PdfReader(io.BytesIO(response.content)).pages:
                page.extract_text(visitor_text=visit)
            assert len(sizes) == 1
            assert abs(sizes[0] - size) < 0.02


def create(client):
    response = client.post('/api/projects', json={
        'name': 'Hala Žďár', 'bay_count': 2, 'default_truss_count': 8,
        'default_height_m': 8.5, 'technician_name': 'Tester',
    })
    assert response.status_code == 201
    return response.json()


def side(client, truss, side, method):
    response = client.put(f'/api/trusses/{truss["id"]}/access/{side}', json={
        'method': method, 'expected_version': truss['version'], 'technician_name': 'Tester',
    })
    assert response.status_code == 200, response.text
    return response.json()


def test_heights_inherit_override_and_clear(client):
    project = create(client)
    a, b = project['bays']
    assert a['effective_height_m'] == b['effective_height_m'] == 8.5
    response = client.put(f'/api/bays/{b["id"]}/height', json={
        'height_m': 12, 'expected_revision': project['revision'], 'technician_name': 'Tester',
    })
    assert response.status_code == 200
    project = response.json()
    assert [bay['effective_height_m'] for bay in project['bays']] == [8.5, 12]
    response = client.put(f'/api/projects/{project["id"]}/height', json={
        'height_m': 9, 'expected_revision': project['revision'], 'technician_name': 'Tester',
    })
    project = response.json()
    assert [bay['effective_height_m'] for bay in project['bays']] == [9, 12]
    response = client.put(f'/api/bays/{b["id"]}/height', json={
        'height_m': None, 'expected_revision': project['revision'], 'technician_name': 'Tester',
    })
    assert response.json()['bays'][1]['effective_height_m'] == 9
    assert client.put(f'/api/projects/{project["id"]}/height', json={
        'height_m': 7, 'expected_revision': 1, 'technician_name': 'Tester',
    }).status_code == 409
    assert client.put(f'/api/projects/{project["id"]}/height', json={
        'height_m': -1, 'expected_revision': 4, 'technician_name': 'Tester',
    }).status_code == 422


def test_independent_sides_note_and_audit(client, db):
    project = create(client)
    truss = project['bays'][0]['trusses'][0]
    for code in ['N', 'K', 'Ž', 'L', 'J']:
        truss = side(client, truss, 'left', code)
        assert truss['right_access'] is None
    truss = side(client, truss, 'right', 'Ž')
    response = client.put(f'/api/trusses/{truss["id"]}/access-note', json={
        'note': 'Přístup přes žeriavovou dráhu <ověřit>', 'expected_version': truss['version'], 'technician_name': 'Tester',
    })
    assert response.status_code == 200
    truss = response.json()
    assert truss['left_access'] == 'J' and truss['right_access'] == 'Ž'
    assert not truss['left_done'] and not truss['right_done']
    assert truss['exclusion_note'] is None
    truss = side(client, truss, 'left', None)
    assert truss['right_access'] == 'Ž' and truss['access_note'].endswith('<ověřit>')
    assert db.scalars(select(AuditLog).where(AuditLog.action == 'truss.access.changed')).all()
    assert client.put(f'/api/trusses/{truss["id"]}/access/left', json={
        'method': 'X', 'expected_version': truss['version'], 'technician_name': 'Tester',
    }).status_code == 422


def test_bulk_is_atomic_scoped_and_preserves_other_side(client):
    project = create(client)
    bay = project['bays'][0]
    first, second = bay['trusses'][:2]
    first = side(client, first, 'right', 'J')
    payload = {'technician_name': 'Tester', 'left_access': 'N', 'items': [
        {'truss_id': first['id'], 'expected_version': first['version']},
        {'truss_id': second['id'], 'expected_version': 99},
    ]}
    endpoint = f'/api/bays/{bay["id"]}/access/bulk'
    assert client.post(endpoint, json=payload).status_code == 409
    assert client.get(f'/api/bays/{bay["id"]}').json()['trusses'][0]['left_access'] is None
    payload['items'][1]['expected_version'] = second['version']
    response = client.post(endpoint, json=payload)
    assert response.status_code == 200, response.text
    changed = response.json()['changed']
    assert len(changed) == 2 and all(t['left_access'] == 'N' for t in changed)
    assert changed[0]['right_access'] == 'J'
    foreign = project['bays'][1]['trusses'][0]
    payload['items'] = [{'truss_id': foreign['id'], 'expected_version': foreign['version']}]
    assert client.post(endpoint, json=payload).status_code == 422
    client.post(f'/api/projects/{project["id"]}/archive', json={'technician_name': 'Tester'})
    payload['items'] = [{'truss_id': changed[0]['id'], 'expected_version': changed[0]['version']}]
    assert client.post(endpoint, json=payload).status_code == 409


def test_access_layers_in_svg_and_both_pdf_exports(client):
    project = create(client)
    bay = project['bays'][0]
    truss = side(client, bay['trusses'][0], 'left', 'Ž')
    truss = side(client, truss, 'right', 'K')
    client.put(f'/api/trusses/{truss["id"]}/access-note', json={
        'note': 'Unikátní poznámka k přístupu', 'expected_version': truss['version'], 'technician_name': 'Tester',
    })
    for enabled in (False, True):
        query = f'show_access={str(enabled).lower()}&page_size=A3&font_size=10'
        svg = client.get(f'/api/projects/{project["id"]}/plan.svg?{query}').text
        assert ('data-access-legend' in svg) == enabled
        assert ('data-access-side="left"' in svg) == enabled
        assert ('Výška: 8,5 m' in svg) == enabled
        for kind, endpoint in [('project', f'/api/projects/{project["id"]}/plan.pdf'), ('bay', f'/api/bays/{bay["id"]}/report.pdf')]:
            response = client.get(f'{endpoint}?{query}')
            assert response.status_code == 200, response.text
            reader = PdfReader(io.BytesIO(response.content))
            if kind == 'project':
                assert len(reader.pages) == 1
            text = '\n'.join(page.extract_text() for page in reader.pages)
            assert ('N = Nůžková plošina' in text) == enabled
            assert ('Výška: 8,5 m' in text) == enabled
            assert '■' not in text
            if kind == 'bay':
                assert ('Unikátní poznámka' in text) == enabled
            for page in reader.pages:
                assert page.extract_text().count(APP_VERSION) == 1


def test_resize_warns_before_hiding_access_data(client):
    project = create(client)
    bay = project['bays'][0]
    side(client, bay['trusses'][-1], 'left', 'L')
    response = client.post(f'/api/bays/{bay["id"]}/resize', json={
        'truss_count': 7, 'technician_name': 'Tester',
    })
    assert response.status_code == 409 and response.json()['detail']['confirmation_required']
