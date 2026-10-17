import importlib.util
import json
from pathlib import Path
import tarfile

import pytest


spec = importlib.util.spec_from_file_location('capture_sdk_runtime', Path(__file__).resolve().parents[1] / 'scripts/capture_sdk_runtime.py')
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


def selection(source):
    return {'target': 'darwin-arm64', 'sources': [{'source': str(source), 'destination': 'material'}],
            'runtime': {'binary': 'material/runtime', 'arguments': []}, 'configuration': {}, 'provenance': {'test': True}}


def test_capture_pins_all_selected_bytes_and_modes_deterministically(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    runtime = source / 'runtime'; runtime.write_bytes(b'executable'); runtime.chmod(0o755)
    (source / 'LICENSE').write_text('retained license')
    result = capture.capture(selection(source), tmp_path / 'one')
    again = capture.capture(selection(source), tmp_path / 'two')
    assert result == again
    with tarfile.open(tmp_path / 'one' / result['bundle_file']) as archive:
        assert archive.getmember('material/runtime').mode == 0o555
        assert archive.extractfile('material/LICENSE').read() == b'retained license'
        manifest = json.load(archive.extractfile('manifest.json'))
        assert set(manifest['files']) == {'material/runtime', 'material/LICENSE'}
    runtime.write_bytes(b'different executable')
    assert capture.capture(selection(source), tmp_path / 'changed')['bundle_digest'] != result['bundle_digest']


def test_capture_refuses_escaping_material_links(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    outside = tmp_path / 'outside'; outside.write_bytes(b'outside')
    (source / 'runtime').symlink_to(outside)
    with pytest.raises(ValueError, match='leaves selected tree'):
        capture.capture(selection(source), tmp_path / 'output')
