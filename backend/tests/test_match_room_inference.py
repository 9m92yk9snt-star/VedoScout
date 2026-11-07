import sys
import types
import numpy as np
import pytest
import match_room_inference as inference


def test_default_keeps_existing_nonworker_opencv_loader(monkeypatch):
    monkeypatch.delenv('SCOUTMEPLAY_MATCHROOM_ENGINE',raising=False)
    sentinel=object()
    monkeypatch.setattr(inference.cv2.dnn,'readNetFromONNX',lambda path:sentinel)
    assert inference.load_cpu_net('pinned.onnx') is sentinel


def test_owned_worker_preserves_model_tensor_and_output_order(monkeypatch):
    calls=[]
    setup=[]
    class Options: pass
    class Session:
        def __init__(self,path,*,sess_options,providers):
            assert setup == ['telemetry_disabled']
            assert path=='pinned.onnx'
            assert providers==['CPUExecutionProvider']
            assert sess_options.intra_op_num_threads==sess_options.inter_op_num_threads==1
        def get_inputs(self):return [types.SimpleNamespace(name='images')]
        def get_outputs(self):return [types.SimpleNamespace(name='detections'),types.SimpleNamespace(name='masks')]
        def run(self,names,inputs):calls.append((names,inputs));return ['raw-detections','raw-masks']
    monkeypatch.setitem(sys.modules,'onnxruntime',types.SimpleNamespace(
        disable_telemetry_events=lambda:setup.append('telemetry_disabled'),
        SessionOptions=Options,InferenceSession=Session))
    monkeypatch.setenv('SCOUTMEPLAY_MATCHROOM_ENGINE','onnxruntime')
    model=inference.load_cpu_net('pinned.onnx');pixels=np.zeros((1,3,640,640),np.float32);model.setInput(pixels)
    assert model.forward(model.getUnconnectedOutLayersNames())==['raw-detections','raw-masks']
    assert calls[0][0]==['detections','masks']
    assert calls[0][1]['images'] is pixels


def test_unknown_engine_is_rejected(monkeypatch):
    monkeypatch.setenv('SCOUTMEPLAY_MATCHROOM_ENGINE','unknown')
    with pytest.raises(ValueError):inference.load_cpu_net('pinned.onnx')
