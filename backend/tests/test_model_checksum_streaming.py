"""Every existing model byte is still verified with bounded read buffers."""
import hashlib
from pathlib import Path
import pytest
from player_segmentation_assets import ensure_model_asset

@pytest.mark.parametrize('size',[0,1,1024*1024-1,1024*1024,1024*1024+13,3*1024*1024+7])
def test_streamed_checksum_matches_full_file(tmp_path,monkeypatch,size):
    data=(bytes(range(256))*((size+255)//256))[:size]
    p=tmp_path/'model.onnx';p.write_bytes(data)
    expected=hashlib.sha256(data).hexdigest()
    def forbidden(*args):raise AssertionError('whole-model read')
    monkeypatch.setattr(Path,'read_bytes',forbidden)
    assert ensure_model_asset(p,expected)==p
    if size:
        with p.open('r+b') as f:f.seek(size-1);f.write(bytes([data[-1]^1]))
        with pytest.raises(ValueError,match='checksum'):ensure_model_asset(p,expected)

def test_existing_model_is_checked_again_after_replacement(tmp_path):
    p=tmp_path/'model.onnx';p.write_bytes(b'first')
    sha=hashlib.sha256(b'first').hexdigest();ensure_model_asset(p,sha)
    other=tmp_path/'next';other.write_bytes(b'other');other.replace(p)
    with pytest.raises(ValueError,match='checksum'):ensure_model_asset(p,sha)
