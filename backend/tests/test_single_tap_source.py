import hashlib
import json
from scripts.run_matchroom_single_tap_trial import prepare


def test_selected_original_tap_is_preserved_without_extra_identity_inputs(tmp_path):
    source = tmp_path / 'source'
    parts = source / 'video-parts'
    parts.mkdir(parents=True)
    for i in range(43):
        (parts / f'{i:03}.bin').write_bytes(bytes([i]))
    anchors = [{'t': i, 'box': {'x': .1, 'y': .2, 'w': .2, 'h': .3},
                'target_point': {'x': .2, 'y': .3}} for i in range(5)]
    data = json.dumps({'raw_marker_anchors': anchors}).encode()
    (source / 'anchors.json').write_bytes(data)
    (source / 'SHA256SUMS').write_text(
        hashlib.sha256(bytes(range(43))).hexdigest() + '  video/source.mp4\n' +
        hashlib.sha256(data).hexdigest() + '  anchors.json\n')
    video, selection = prepare(source, tmp_path / 'work', tap_index=4)
    assert video.read_bytes() == bytes(range(43))
    assert selection == {'raw_marker_anchors': [anchors[4]]}
    assert json.loads((source / 'anchors.json').read_text())['raw_marker_anchors'] == anchors
