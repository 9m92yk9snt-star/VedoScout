"""Discarded off-image boxes must not consume mask-decoder work."""
import numpy as np
import pytest
import native_player_segmentation as native


class Net:
    def __init__(self, boxes):
        self.rows = np.zeros((1, 116, len(boxes)), np.float32)
        for i, box in enumerate(boxes):
            self.rows[0, :4, i] = box
            self.rows[0, 4, i] = .9
        self.prototypes = np.zeros((1, 32, 160, 160), np.float32)
    def setInput(self, value):
        pass
    def getUnconnectedOutLayersNames(self):
        return ['boxes', 'masks']
    def forward(self, names):
        return [self.rows, self.prototypes]


@pytest.mark.parametrize('outside', [(-50, 100, 20, 20), (700, 100, 20, 20), (100, -50, 20, 20), (100, 700, 20, 20)])
def test_outside_box_skips_decoder_preserving_valid_mask(monkeypatch, outside):
    model = native.PersonSegmenter.__new__(native.PersonSegmenter)
    model.net = Net([outside, (100, 100, 20, 20)])
    calls=[];original=np.exp
    def exp(value):
        calls.append(1)
        return original(value)
    monkeypatch.setattr(native.np, 'exp', exp)
    result=model.predict(np.zeros((640,640,3),np.uint8))
    assert calls==[1]
    assert len(result)==1 and result[0]['box']==(90,90,20,20)
    expected=np.zeros((640,640),np.uint8);expected[90:110,90:110]=1
    assert np.array_equal(result[0]['mask'],expected)


def test_discarded_top24_are_not_replaced_with_lower_ranked_detection(monkeypatch):
    model=native.PersonSegmenter.__new__(native.PersonSegmenter)
    model.net=Net([(-50,100,20,20)]*24+[(100,100,20,20)])
    monkeypatch.setattr(native.cv2.dnn,'NMSBoxes',lambda boxes,*a:np.arange(len(boxes)))
    monkeypatch.setattr(native.np,'exp',lambda value:pytest.fail('No retained box needs a mask'))
    assert model.predict(np.zeros((640,640,3),np.uint8))==[]
