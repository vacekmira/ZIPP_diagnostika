from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from lxml import html
from sqlalchemy import func, select

from app.models import AuditLog, Bay, Project, Truss


ROOT = Path(__file__).resolve().parents[1]


def create(client):
    response = client.post('/api/projects', json={
        'name': 'Společná hala Žďár', 'bay_count': 2, 'default_truss_count': 4,
        'default_height_m': 8.5, 'technician_name': 'Zakladatel',
    })
    assert response.status_code == 201
    return response.json()


def page(client, url, mode):
    response = client.get(f'{url}?mode={mode}')
    assert response.status_code == 200, response.text
    document = html.fromstring(response.text)
    assert document.xpath('//body/@data-work-mode') == [mode]
    assert document.xpath('//a[@aria-current="page"]/@data-work-mode-link') == [mode]
    return document


def geometry(document):
    return [(node.get('data-truss-id'), node.get('data-position'), node.get('data-truss-type'),
             node.get('data-pair-id'), node.xpath('.//*[@data-label]/text()')[0])
            for node in document.xpath('//article[@data-truss-id]')]


def test_modes_read_the_same_rows_without_creating_any_data(client, db):
    project = create(client)
    counts = lambda: [db.scalar(select(func.count()).select_from(model)) for model in (Project, Bay, Truss, AuditLog)]
    before = counts()
    bay_cards = []
    for mode in ('diagnostics', 'survey'):
        document = page(client, f'/projects/{project["id"]}', mode)
        bay_cards.append(document.xpath('//a[@data-bay-card-id]/@data-bay-card-id'))
    assert bay_cards[0] == bay_cards[1] == [str(bay['id']) for bay in project['bays']]
    for bay in project['bays']:
        diagnostic = geometry(page(client, f'/bays/{bay["id"]}', 'diagnostics'))
        survey = geometry(page(client, f'/bays/{bay["id"]}', 'survey'))
        assert diagnostic == survey
        assert [row[0] for row in diagnostic] == [str(truss['id']) for truss in bay['trusses']]
    assert counts() == before
    assert client.get(f'/bays/{project["bays"][0]["id"]}').status_code == 200
    assert client.get(f'/projects/{project["id"]}?mode=unknown').status_code == 422


def test_working_screens_and_audit_do_not_mix_the_two_sets_of_fields(client):
    project = create(client)
    bay = project['bays'][0]
    truss = bay['trusses'][0]
    truss = client.put(f'/api/trusses/{truss["id"]}/access-note', json={
        'note': 'Poznámka jen pro obhlídku', 'expected_version': truss['version'], 'technician_name': 'Obhlídkář',
    }).json()
    result = client.post(f'/api/trusses/{truss["id"]}/exclude', json={
        'reason': 'crack', 'note': 'Poznámka jen pro diagnostiku', 'expected_version': truss['version'], 'technician_name': 'Diagnostik',
    })
    assert result.status_code == 200
    for url in (f'/projects/{project["id"]}', f'/bays/{bay["id"]}', f'/trusses/{truss["id"]}'):
        diagnostic = page(client, url, 'diagnostics')
        survey = page(client, url, 'survey')
        assert not diagnostic.xpath('//*[@data-height-form or @data-access-method or @data-edit-access-note or @data-select-mode]')
        assert not survey.xpath('//*[@data-side or @data-exclude-form or @data-restore or @data-bay-progress]')
        assert not survey.xpath('//*[contains(concat(" ", normalize-space(@class), " "), " is-excluded ")]')
        assert 'Poznámka jen pro diagnostiku' not in survey.xpath('//main')[0].text_content()
        assert 'Poznámka jen pro obhlídku' not in diagnostic.xpath('//main')[0].text_content()
    diagnostic = page(client, f'/trusses/{truss["id"]}', 'diagnostics')
    survey = page(client, f'/trusses/{truss["id"]}', 'survey')
    assert 'Diagnostik' in diagnostic.xpath('//div[@class="audit-list"]')[0].text_content()
    assert 'Obhlídkář' not in diagnostic.xpath('//div[@class="audit-list"]')[0].text_content()
    assert 'Obhlídkář' in survey.xpath('//div[@class="audit-list"]')[0].text_content()
    assert 'Diagnostik' not in survey.xpath('//div[@class="audit-list"]')[0].text_content()


def test_changing_either_mode_preserves_the_other_values(client):
    project = create(client)
    bay = project['bays'][0]
    truss = bay['trusses'][0]
    truss = client.put(f'/api/trusses/{truss["id"]}/diagnostics/left', json={
        'done': True, 'expected_version': truss['version'], 'technician_name': 'Diagnostik',
    }).json()
    for side, method in (('left', 'Ž'), ('right', 'K')):
        response = client.put(f'/api/trusses/{truss["id"]}/access/{side}', json={
            'method': method, 'expected_version': truss['version'], 'technician_name': 'Obhlídkář',
        })
        assert response.status_code == 200
        truss = response.json()
        assert truss['left_done'] and not truss['right_done'] and not truss['excluded']
    truss = client.put(f'/api/trusses/{truss["id"]}/access-note', json={
        'note': 'Žebřík vedle sloupu', 'expected_version': truss['version'], 'technician_name': 'Obhlídkář',
    }).json()
    before = {key: truss[key] for key in ('left_access', 'right_access', 'access_note')}
    truss = client.put(f'/api/trusses/{truss["id"]}/diagnostics/right', json={
        'done': True, 'expected_version': truss['version'], 'technician_name': 'Diagnostik',
    }).json()
    assert {key: truss[key] for key in before} == before
    current = client.get(f'/api/projects/{project["id"]}').json()
    assert current['default_height_m'] == current['bays'][0]['effective_height_m'] == 8.5
    assert truss['left_done'] and truss['right_done']


def test_shared_labels_counts_types_and_pairs_are_visible_in_both_modes(client):
    project = create(client)
    bay = project['bays'][0]
    first, second, third = bay['trusses'][:3]
    response = client.patch(f'/api/trusses/{first["id"]}/label', json={
        'label': 'Historické V-01', 'expected_version': first['version'], 'technician_name': 'Tester',
    })
    assert response.status_code == 200
    first = response.json()
    assert client.patch(f'/api/trusses/{first["id"]}/type', json={
        'type': 'gable', 'expected_version': first['version'], 'technician_name': 'Tester',
    }).status_code == 200
    assert client.post(f'/api/bays/{bay["id"]}/dilation-pairs', json={
        'truss_a_id': second['id'], 'truss_b_id': third['id'],
        'expected_version_a': second['version'], 'expected_version_b': third['version'], 'technician_name': 'Tester',
    }).status_code == 201
    assert client.post(f'/api/bays/{bay["id"]}/resize', json={'truss_count': 6, 'technician_name': 'Tester'}).status_code == 200
    a = geometry(page(client, f'/bays/{bay["id"]}', 'diagnostics'))
    b = geometry(page(client, f'/bays/{bay["id"]}', 'survey'))
    assert a == b and len(a) == 6
    assert a[0][2] == 'gable' and a[0][4] == 'Historické V-01'
    assert a[1][3] == a[2][3] and a[1][3]
    assert [int(row[0]) for row in a[:4]] == [truss['id'] for truss in bay['trusses']]


def test_mode_navigation_and_export_options_are_shared(client):
    project = create(client)
    bay = project['bays'][0]
    truss = bay['trusses'][0]
    for url in (f'/projects/{project["id"]}', f'/bays/{bay["id"]}', f'/bays/{bay["id"]}/settings',
                f'/trusses/{truss["id"]}', f'/projects/{project["id"]}/plan'):
        document = page(client, url, 'survey')
        for target in document.xpath('//a[not(@data-work-mode-link)]/@href'):
            if target.startswith(('/projects/', '/bays/', '/trusses/')):
                assert 'mode=survey' in target
    signatures = []
    for mode in ('diagnostics', 'survey'):
        for url in (f'/bays/{bay["id"]}', f'/projects/{project["id"]}/plan'):
            document = page(client, url, mode)
            signatures.append(document.xpath('//*[@data-export-form]//option/@value'))
            assert document.xpath('//*[@data-export-form]//input[@name="show_access"]/@value') == ['false', 'true']
    assert all(signature == signatures[0] for signature in signatures)
    assert signatures[0] == ['A4', 'A3', 'A2', 'A1', 'A0', 'landscape', 'portrait', 'auto', '7', '9', '10', '12', '14']
    client.cookies.set('zipp_language', 'sk')
    document = page(client, f'/bays/{bay["id"]}', 'survey')
    assert document.xpath('//a[@data-work-mode-link="survey"]/text()') == ['Obhliadka']


def test_alpha9_needs_no_additional_schema_and_archives_stay_readonly(client):
    assert not list((ROOT / 'migrations/versions').glob('*alpha9*'))
    project = create(client)
    bay = project['bays'][0]
    client.post(f'/api/projects/{project["id"]}/archive', json={'technician_name': 'Tester'})
    for mode in ('diagnostics', 'survey'):
        document = page(client, f'/bays/{bay["id"]}', mode)
        for node in document.xpath('//*[@data-side or @data-access-method or @data-edit-access-note or @data-select-mode]'):
            assert node.get('disabled') is not None
    document = page(client, f'/trusses/{bay["trusses"][0]["id"]}', 'survey')
    assert all(node.get('disabled') is not None for node in document.xpath('//*[@data-access-method]'))


def test_survey_link_survives_login_redirect(client):
    project = create(client)
    target = f'/bays/{project["bays"][0]["id"]}?mode=survey'
    client.cookies.clear()
    response = client.get(target, follow_redirects=False)
    assert response.status_code == 303
    next_url = response.headers['location']
    assert parse_qs(urlsplit(next_url).query)['next'] == [target]
    login = html.fromstring(client.get(next_url).text)
    assert login.xpath('//input[@name="next"]/@value') == [target]
    response = client.post('/login', data={'password': 'test-password-123', 'next': target}, follow_redirects=False)
    assert response.status_code == 303 and response.headers['location'] == target
    assert html.fromstring(client.get(target).text).xpath('//body/@data-work-mode') == ['survey']
