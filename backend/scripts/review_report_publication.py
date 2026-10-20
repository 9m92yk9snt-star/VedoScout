#!/usr/bin/env python3
"""Render an existing evidence export offline. Never imports server or calls a model."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from report_publication import publish_report
from pdf_v2 import build_pdf_v2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = json.loads((args.evidence_dir / 'report.json').read_text())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    images = output / 'frames'
    images.mkdir(exist_ok=True)
    local = {}
    videos = list((args.evidence_dir / 'video').glob('*.mp4'))
    if videos:
        import cv2
        from video_timebase import read_frame_at
        cap = cv2.VideoCapture(str(videos[0]))
        try:
            for comment in report.get('full_report', {}).get('video_comments', []):
                ms = comment.get('evidence_time_ms')
                if not isinstance(ms, int):
                    continue
                ok, pixels, actual = read_frame_at(cap, ms / 1000)
                if not ok or round(actual * 1000) != ms:
                    raise ValueError('Stored proof does not match exported source PTS')
                image = images / (comment['event_id'] + '.jpg')
                cv2.imwrite(str(image), pixels)
                local[comment.get('frame_url')] = str(image)
            anchors = report.get('anchors') or []
            if anchors:
                anchor = anchors[0]
                box = anchor.get('box') or {}
                ok, pixels, _ = read_frame_at(cap, anchor['t'])
                if ok and all(k in box for k in ('x','y','w','h')):
                    h, w = pixels.shape[:2]
                    x0, y0 = max(0, int((box['x']-.25*box['w'])*w)), max(0, int((box['y']-.1*box['h'])*h))
                    x1, y1 = min(w, int((box['x']+1.25*box['w'])*w)), min(h, int((box['y']+1.1*box['h'])*h))
                    image = images / 'player-from-original-anchor.jpg'
                    if x1 > x0 and y1 > y0:
                        crop = pixels[y0:y1,x0:x1]
                        scale = max(1, 120/crop.shape[1], 120/crop.shape[0])
                        crop = cv2.resize(crop, None, fx=scale, fy=scale)
                        cv2.imwrite(str(image), crop)
                        for key in ('player_photo_url_override','display_crop_url_override','subject_crop_url_override'):
                            local[report.get(key)] = str(image)
                        for key in ('player_photo_filename','display_crop_filename','subject_crop_filename','marker_filename'):
                            if report.get(key):
                                local['/api/uploads/'+report[key]] = str(image)
        finally:
            cap.release()
    published = publish_report(report)
    pdf = output / 'Orman500_Report_Review.pdf'
    build_pdf_v2(published, str(pdf), image_resolver=lambda url: local.get(url))
    (output / 'published-report.json').write_text(json.dumps(published, ensure_ascii=False))
    print(json.dumps({'pdf': str(pdf), 'score': published.get('report_publication', {}).get('score'),
        'events': len(published['full_report'].get('action_timeline', [])), 'model_calls': 0}, indent=2))


if __name__ == '__main__':
    main()
