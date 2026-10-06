"""Static checks for the swarm web UI package."""

from pathlib import Path


def root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_ui_has_no_external_runtime_assets():
    html = (root() / 'static' / 'index.html').read_text(encoding='utf-8')
    assert 'https://' not in html
    assert 'http://' not in html
    assert '<script src=' not in html
    assert '<link rel="stylesheet"' not in html


def test_ui_states_unicast_synchronization_boundary():
    html = (root() / 'static' / 'index.html').read_text(encoding='utf-8')
    assert 'not</strong> Crazyradio broadcast' in html
    assert 'do not provide hard synchronization' in html


def test_example_config_is_json():
    import json

    data = json.loads((root() / 'config' / 'fleet.example.json').read_text(encoding='utf-8'))
    assert data['drones']
    assert isinstance(data['groups'], dict)
