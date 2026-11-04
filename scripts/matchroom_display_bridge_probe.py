"""Replay the approved presentation using the shared display implementation."""
import sys
import numpy as np
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from match_room_display_bridge import display_bridge


if __name__ == '__main__':
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validation', required=True)
    args = parser.parse_args()
    evidence = json.loads(Path(args.validation).read_text())
    result = display_bridge(**evidence['bridge_inputs'])
    expected = evidence['bridge_result']
    assert all(np.allclose(a['display_position_px'],b['display_position_px'],atol=1e-8)
               for a,b in zip(result['samples'],expected['samples']))
    assert len(result['samples']) == len(expected['samples'])
    print(json.dumps({'source_camera_replay': True, 'frames': len(result['samples']),
                      'report_identity_approved': False}))
