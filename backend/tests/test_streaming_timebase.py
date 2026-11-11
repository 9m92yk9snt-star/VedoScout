import video_timebase as v


def test_stream_is_lazy_and_reuses_forward_decoding(monkeypatch):
    calls=[]
    class Cap:
        def retrieve(self):
            calls.append('retrieve')
            return True, object()
    ticks=iter([.125,.25])
    monkeypatch.setattr(v,'seek_with_preroll',lambda *a:(calls.append('seek') or (True,0.,False)))
    monkeypatch.setattr(v,'grab_frame_time_seconds',lambda *a:(True,next(ticks),False))
    stream=v.iter_frames_at(Cap(),[0,125,250])
    assert calls==[]
    assert next(stream)[0]==0
    assert calls==['seek','retrieve']
    assert [k for k,_ in stream]==[125,250]
    assert calls==['seek','retrieve','retrieve','retrieve']


def test_fallback_time_is_not_emitted(monkeypatch):
    monkeypatch.setattr(v,'seek_with_preroll',lambda *a:(True,.1,True))
    assert list(v.iter_frames_at(object(),[100]))==[]
