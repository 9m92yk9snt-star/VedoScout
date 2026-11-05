"""No model calls: preserve evidence while bounding each actual request."""
from copy import deepcopy
import pytest
from scripts.run_sequence_pilot import bounded_detail_packets


def scene():
    frames = [{"frame_id": str(i), "media_ms": i * 20} for i in range(200)]
    overview = [f["frame_id"] for f in frames if int(f["frame_id"]) % 6 == 0]
    for f in frames:
        if f["frame_id"] in overview:
            f["zoom_view"] = {"sha256": "original-detail"}
    packet = {"packet_id": "review", "phase": "FOLLOWUP", "start_ms": 0, "end_ms": 3980,
              "frame_ids": [f["frame_id"] for f in frames], "reference_ids": ["original-tap"],
              "replaces_initial_packet_id": "sequence_001"}
    return packet, {"frames": frames}, overview


def test_windows_keep_all_context_detail_and_overlap_without_mutation():
    packet, manifest, overview = scene()
    original = deepcopy((packet, manifest))
    parts = bounded_detail_packets(packet, manifest, overview,
        lambda p: len(p.get("detail_frame_ids", p["frame_ids"])) <= 115)
    assert len(parts) == 2
    assert (packet, manifest) == original
    assert set().union(*(set(p["detail_frame_ids"]) for p in parts)) == set(packet["frame_ids"])
    overlap = set(parts[0]["detail_frame_ids"]) & set(parts[1]["detail_frame_ids"])
    assert len(overlap) >= 12
    assert len({p["packet_id"] for p in parts}) == len(parts)
    for p in parts:
        assert set(overview) <= set(p["frame_ids"])
        assert p["reference_ids"] == packet["reference_ids"]
        assert (p["start_ms"], p["end_ms"]) == (0, 3980)
        assert p["replaces_initial_packet_id"] == "sequence_001"


def test_fitting_request_is_unchanged_and_initial_never_split():
    packet, manifest, overview = scene()
    assert bounded_detail_packets(packet, manifest, overview, lambda p: True) == [packet]
    packet["phase"] = "INITIAL"
    with pytest.raises(ValueError, match="REQUEST_IMAGE_BUDGET_EXCEEDED"):
        bounded_detail_packets(packet, manifest, overview, lambda p: False)


def test_irreducible_context_stops_instead_of_dropping_evidence():
    packet, manifest, overview = scene()
    calls = []
    def reject(p):
        calls.append(p)
        return False
    with pytest.raises(ValueError, match="REQUEST_IMAGE_BUDGET_EXCEEDED"):
        bounded_detail_packets(packet, manifest, overview, reject)
    assert len(calls) <= 5



def test_initial_split_keeps_all_pixels_references_and_actual_wire_limit(tmp_path):
    import hashlib
    import json
    import sequence_pilot_transport as transport
    from scripts.run_sequence_pilot import bounded_initial_packets
    # Transport fixture: byte content is not decoded or sent to a model.
    image = tmp_path/'source.jpg'
    image.write_bytes(b'x'*260_000)
    sha = hashlib.sha256(image.read_bytes()).hexdigest()
    frames = [{"frame_id": str(i), "media_ms": i*100} for i in range(80)]
    packet = {"packet_id":"sequence_005", "phase":"INITIAL", "start_ms":0,
              "end_ms":7900, "core_start_ms":0, "core_end_ms":7901,
              "frame_ids":[f['frame_id'] for f in frames], "reference_ids":["tap"]}
    def wire(p):
        return transport.build_request('emergent','gemini-2.5-pro',
            [{"type":"text","text":json.dumps(p)}]+[
             {"type":"image","path":str(image),"sha256":sha} for _ in ['tap']+p['frame_ids']])
    def fits(p):
        try: wire(p); return True
        except ValueError as e:
            assert str(e)=='REQUEST_IMAGE_BUDGET_EXCEEDED'
            return False
    original=deepcopy(packet)
    parts=bounded_initial_packets(packet,{"frames":frames},fits)
    assert len(parts)==2
    assert packet==original
    assert set().union(*(set(p['frame_ids']) for p in parts))==set(packet['frame_ids'])
    overlap=set(parts[0]['frame_ids'])&set(parts[1]['frame_ids'])
    assert len(overlap)>=10
    for p in parts:
        assert p['reference_ids']==['tap']
        _,payload,audit=wire(p)
        assert len(payload)<=transport.MAX_REQUEST_BYTES
        assert all(i['sha256']==sha for i in audit['images'])
    assert parts==bounded_initial_packets(packet,{"frames":frames},fits)
    assert bounded_initial_packets(parts[0],{'frames':frames},fits)==[parts[0]]


def test_initial_split_has_bounded_work_and_keeps_small_packets_identical():
    from scripts.run_sequence_pilot import bounded_initial_packets
    packet, manifest, _ = scene()
    packet['phase']='INITIAL'
    assert bounded_initial_packets(packet,manifest,lambda p:True)[0] is packet
    with pytest.raises(ValueError,match='REQUEST_IMAGE_BUDGET_EXCEEDED'):
        bounded_initial_packets(packet,manifest,lambda p:False)


def test_retry_code_migration_is_narrow_and_payload_still_must_match():
    import hashlib
    from sequence_run_checkpoint import retry_code_compatible, _PRE_SPLIT_CODE, reusable_receipt
    current={**_PRE_SPLIT_CODE,'run_sequence_pilot.py':'new','sequence_run_checkpoint.py':'new',
             'sequence_report_runtime.py':'new'}
    assert retry_code_compatible(_PRE_SPLIT_CODE,current)
    assert not retry_code_compatible({},current)
    assert not retry_code_compatible(_PRE_SPLIT_CODE,{**current,'sequence_pilot.py':'changed-prompt'})
    r=dict(packet_id='sequence_001',origin='LIVE_MODEL_REQUEST',status='COMPLETED',provider='emergent',
           requested_model='gemini-2.5-pro',payload_sha256='same',raw_response='{}',
           response_sha256=hashlib.sha256(b'{}').hexdigest())
    assert reusable_receipt(r,{'payload_sha256':'same'},provider='emergent',model='gemini-2.5-pro',packet_id='sequence_001')
    assert not reusable_receipt(r,{'payload_sha256':'different'},provider='emergent',model='gemini-2.5-pro',packet_id='sequence_001')


def test_rate_limit_release_migration_keeps_exact_request_gate():
    from sequence_run_checkpoint import retry_code_compatible, _PRE_RATE_LIMIT_CODE, code_fingerprint
    current = code_fingerprint()
    assert retry_code_compatible(_PRE_RATE_LIMIT_CODE, current)
    for field in ('sequence_pilot.py', 'player_selection.py', 'match_room.py', 'sequence_report_adapter.py'):
        assert not retry_code_compatible(_PRE_RATE_LIMIT_CODE, {**current, field: 'changed'})
    assert not retry_code_compatible({**_PRE_RATE_LIMIT_CODE, 'sequence_pilot_transport.py': 'unknown'}, current)


def test_failed_retry_cannot_erase_intact_completed_response():
    import hashlib
    from sequence_run_checkpoint import merge_retry_receipts
    good = dict(packet_id='one', status='COMPLETED', origin='LIVE_MODEL_REQUEST',
                provider='emergent', requested_model='gpt-6-astra', payload_sha256='old',
                raw_response='{}', response_sha256=hashlib.sha256(b'{}').hexdigest())
    for status in ('NOT_SENT', 'ERROR', 'INVALID_OBSERVATION_RESPONSE'):
        assert merge_retry_receipts([good], [dict(packet_id='one', status=status)]) == [good]
    newer = {**good, 'payload_sha256': 'new'}
    assert merge_retry_receipts([good], [newer]) == [newer]
    failed = dict(packet_id='one', status='ERROR')
    assert merge_retry_receipts([{**good, 'raw_response':'damaged'}], [failed]) == [failed]
