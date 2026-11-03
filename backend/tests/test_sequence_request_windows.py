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
