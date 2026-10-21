"""Reading-first Sequence PDF. All facts come from the shared publication view."""
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont, TTFError
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak,
    KeepTogether, CondPageBreak,
)

PAGE_W, PAGE_H = A4
MARGIN = 34
WIDTH = PAGE_W - 2 * MARGIN
GREEN = colors.HexColor('#12402A')
INK = colors.HexColor('#22382B')
MUTED = colors.HexColor('#627168')
LINE = colors.HexColor('#DCE4DA')
PALE = colors.HexColor('#F0F5EC')
GOLD = colors.HexColor('#D7AE4B')
BODY, BOLD, DISPLAY = 'Helvetica', 'Helvetica-Bold', 'Helvetica-Bold'
try:
    for name, filename in [('SequenceBody', 'DMSans-Regular.ttf'),
                           ('SequenceBold', 'Barlow-Bold.ttf'),
                           ('SequenceDisplay', 'Barlow-Black.ttf')]:
        pdfmetrics.registerFont(TTFont(name, str(Path(__file__).parent / 'fonts' / filename)))
    BODY, BOLD, DISPLAY = 'SequenceBody', 'SequenceBold', 'SequenceDisplay'
    pdfmetrics.registerFontFamily('SequenceBody', normal=BODY, bold=BOLD, italic=BODY, boldItalic=BOLD)
except (OSError, ValueError, TTFError):
    pass


def p(text, size=10, color=INK, bold=False, leading=None):
    return Paragraph(str(text), ParagraphStyle(
        'copy', fontName=BOLD if bold else BODY, fontSize=size, textColor=color,
        leading=leading or size * 1.42, spaceAfter=0,
    ))


def safe(text):
    return escape(str(text or ''))


def section(number, title, deck):
    return [p(f'{number} / PLAYER REPORT', 8, MUTED, True), Spacer(1, 5),
            p(safe(title), 25, GREEN, True), Spacer(1, 7),
            p(safe(deck), 10, MUTED), Spacer(1, 18)]


def table(data, widths, *, shade=False, padding=10):
    t = Table(data, colWidths=widths, hAlign='LEFT')
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), padding),
        ('RIGHTPADDING', (0, 0), (-1, -1), padding),
        ('TOPPADDING', (0, 0), (-1, -1), padding),
        ('BOTTOMPADDING', (0, 0), (-1, -1), padding),
        ('BACKGROUND', (0, 0), (-1, -1), PALE if shade else colors.white),
        ('LINEBELOW', (0, 0), (-1, -1), .5, LINE),
    ]))
    return t


def fitted_image(path, width, max_height):
    """Contain the complete source frame. Never crop the player or ball to fill a box."""
    if not path:
        return p('Image unavailable. Open the linked video evidence.', 9, MUTED)
    try:
        with PILImage.open(path) as im:
            iw, ih = im.size
        scale = min(width / iw, max_height / ih)
        return Image(str(path), width=iw * scale, height=ih * scale, hAlign='LEFT')
    except (OSError, TypeError, ValueError):
        return p('Image unavailable. Open the linked video evidence.', 9, MUTED)


def action_image(action, comments, resolve):
    comment = comments.get(action['event_id'], {})
    if comment.get('proof_frame_verified') is not True:
        return None
    return resolve(comment.get('frame_url'))


def action_card(action, index, comments, resolve, width, image_height):
    path = action_image(action, comments, resolve)
    return [fitted_image(path, width, image_height), Spacer(1, 12),
            p(f'{index:02d} / {safe(action["title"])}', 16, GREEN, True), Spacer(1, 7),
            p(safe(action['summary']), 10), Spacer(1, 10),
            p('VIDEO ' + safe(action['timestamp']), 8.5, MUTED, True)]


def category_card(full, category, label, expected):
    rows = [[p(label, 16, GREEN, True), p('GRADE', 8, MUTED, True)]]
    for key in expected:
        from report_publication import label as skill_label
        skill = full.get(category, {}).get(key) or {}
        value = skill.get('score')
        grade = f'{value:.1f}' if isinstance(value, (float, int)) and not skill.get('cannot_evaluate') else '-'
        rows.append([p(safe(skill_label(key)), 9), p(grade, 10, GREEN, True)])
    t = table(rows, [(WIDTH - 16) / 2 - 56, 56], padding=5)
    t.setStyle(TableStyle([('LINEBELOW', (0, 0), (-1, 0), 1.2, GREEN)]))
    return t


def build_sequence_pdf(report, output_path, resolve):
    from report_publication import EXPECTED_SKILLS, CATEGORIES, label as skill_label
    pub, full = report['report_publication'], report['full_report']
    profile = report.get('player_details') or {}
    name = profile.get('player_name') or 'Player'
    score = pub['score']
    actions = pub['key_actions']
    comments = {c['event_id']: c for c in full.get('video_comments', [])}
    story = []

    # 1. A readable overview, with a full-width match frame instead of an upscaled portrait.
    story += [p('PLAYER REPORT', 9, MUTED, True), Spacer(1, 6), p(safe(name), 32, GREEN, True),
              Spacer(1, 5), p(safe(' | '.join(str(x) for x in (
                  profile.get('position'), f'Age {profile["age"]}' if profile.get('age') else None,
                  profile.get('current_club')) if x)), 11, MUTED), Spacer(1, 17)]
    value = f'{score["value"]:.1f}/10' if score['value'] is not None else 'Not rated'
    score_copy = [p('OVERALL SCORE', 9, GREEN, True), p(value, 31, GREEN, True)]
    score_note = [p('A starting point for development', 14, GREEN, True), Spacer(1, 4),
                  p(f'{score["rated_skills"]}/{score["total_skills"]} skills rated. '
                    f'{score["weighted_coverage_pct"]:g}% of the weighted rubric covered.', 10),
                  Spacer(1, 4), p('Provisional score from this clip. Full-match level and long-term potential remain unassessed.', 9, MUTED)]
    story += [table([[score_copy, score_note]], [157, WIDTH - 157], shade=True, padding=13), Spacer(1, 18)]
    cover = next((a for a in actions if a['title'] == 'Goal' and action_image(a, comments, resolve)), None)
    cover = cover or next((a for a in actions if action_image(a, comments, resolve)), None)
    if cover:
        overview = [p('The performance at a glance', 19, GREEN, True), Spacer(1, 9),
                    p(safe(full['parent_summary']['paragraphs'][0]), 11), Spacer(1, 20),
                    p('Inside the report', 15, GREEN, True), Spacer(1, 8)]
        for title, desc in [('Key actions', 'The finishing and passing moments from this video.'),
                            ('Skills & academy reference', 'All four categories in one place.'),
                            ('What to work on next', 'Three priorities and practical exercises.'),
                            ('Evidence & method', 'The complete log and the basis for every grade.')]:
            overview += [p(title, 11, GREEN, True), p(desc, 9, MUTED), Spacer(1, 10)]
        photo = [fitted_image(action_image(cover, comments, resolve), 211, 354), Spacer(1, 5),
                 p('MATCH FRAME / ' + safe(cover['title']).upper(), 8, MUTED, True)]
        story += [table([[photo, overview]], [228, WIDTH - 228], padding=0), Spacer(1, 17)]
    else:
        story += [p('The performance at a glance', 17, GREEN, True), Spacer(1, 6),
                  p(safe(full['parent_summary']['paragraphs'][0]), 11), Spacer(1, 15)]
    counts = full['verified_stats']['observed_counts']
    cells = [[p(str(counts.get(key, 0)), 21, GREEN, True), p(title, 9, MUTED)]
             for key, title in [('goals', 'Goal' if counts.get('goals') == 1 else 'Goals'),
                                ('assists', 'Assists'), ('shots', 'Shots, incl. goals'), ('total_actions', 'Action segments')]]
    story += [table([cells], [WIDTH / 4] * 4, shade=True, padding=9), Spacer(1, 10),
              p(f'Also recorded: {counts.get("key_passes", 0)} ' + ('key pass' if counts.get('key_passes') == 1 else 'key passes') + ', excluding assists; '
                f'{counts.get("duels_contested", 0)} duels, with no win total established.', 8.5, MUTED), Spacer(1, 6),
              p(f'Based on the submitted {safe(pub["duration"])} video. Counts describe this clip; '
                'they are not full-match totals. Technical notes and evidence follow in the appendix.', 8.5, MUTED)]

    # 2. Keep the five key actions together, with no split image or caption.
    if actions:
        batches = [(0, 2, False)] + [(start, start + 3, True) for start in range(2, len(actions), 3)]
        for start, end, compact in batches:
            if start >= len(actions):
                continue
            chunk = actions[start:end]
            assists_only = all(a['title'] == 'Assist' for a in chunk)
            story += [PageBreak()] + section('02', 'Key actions' if start == 0 else 'The assists' if assists_only else 'More key actions',
                'The passes and the teammates who finish the moves.' if start and assists_only else 'Finishing and chance creation, in video order.')
            gap = 18
            col_width = (WIDTH - gap * (len(chunk) - 1)) / len(chunk)
            cards = []
            widths = []
            for index, action in enumerate(chunk, start=start + 1):
                if cards:
                    cards.append('')
                    widths.append(gap)
                cards.append(action_card(action, index, comments, resolve, col_width, 300 if compact else 407))
                widths.append(col_width)
            story += [KeepTogether(table([cards], widths, padding=0)), Spacer(1, 17)]
            if compact and any(a.get('contact_interval_ms') for a in actions[start:end]):
                story += [p('Foot side is unresolved for the crowded releases. No weak-foot grade is assigned.', 9, MUTED)]
            if compact and assists_only:
                story += [Spacer(1, 18), p('Follow the whole move', 17, GREEN, True), Spacer(1, 7),
                          p('Look at the space before the pass, the delivery, and the finish. '
                            'The evidence links in the appendix connect each pass to the teammate who scores.', 10)]

    # 3. Every category and the academy reference are on one connected spread/page.
    story += [PageBreak()] + section('03', 'Skills & academy reference', 'All four categories together. A dash means the clip does not support a grade.')
    cards = [category_card(full, cat, title, EXPECTED_SKILLS[cat])
             for cat, title in zip(CATEGORIES, ('Technique', 'Game understanding', 'Physical', 'Mentality'))]
    grid = Table([[cards[0], '', cards[1]], [cards[2], '', cards[3]]], colWidths=[(WIDTH - 16) / 2, 16, (WIDTH - 16) / 2])
    grid.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                             ('RIGHTPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 12)]))
    story += [KeepTogether(grid), Spacer(1, 9)]
    comp = score.get('comparison')
    if comp:
        story += [p(f'{safe(comp["bracket"])} / {safe(comp["label"])} reference', 17, GREEN, True), Spacer(1, 7)]
        bands = [[p(safe(b['label']), 9, GREEN, True), p(f'{b["min"]:g} - {b["max"]:g}', 10)] for b in comp['ranges']]
        story += [table(bands, [WIDTH * .65, WIDTH * .35], shade=True, padding=5), Spacer(1, 9),
                  p(safe(comp['note']), 8.5, MUTED)]
    story += [Spacer(1, 9), p('This comparison describes the rated skills in the video. It does not place the player on a recruitment ladder.', 8.5, MUTED)]

    # 4. Priorities, practical exercises and parent guidance form one section.
    story += [PageBreak()] + section('04', 'What to work on next', 'Choose one focus at a time. Practise it, then look for it in the next video.')
    priorities = full.get('development_priorities_detailed') or []
    for i, priority in enumerate(priorities, 1):
        story.append(KeepTogether([p(f'{i:02d} / {safe(priority["name"])}', 17, GREEN, True), Spacer(1, 5),
            p(safe(priority['issue']), 10), Spacer(1, 5), p('<b>Try this:</b> ' + safe(priority['how_to_improve']), 10), Spacer(1, 18)]))
    story += [p('A simple practice week', 17, GREEN, True), Spacer(1, 8)]
    drills = (full.get('training_plan') or {}).get('exercises') or []
    # Use retained exercises as general practice, without promising a future performance gain.
    practice = [[p(safe(drill.get('name')), 10, GREEN, True),
                 p(safe(drill.get('description')), 9), p(safe(drill.get('duration')), 9, MUTED)] for drill in drills[:3]]
    if practice:
        story += [table(practice, [112, WIDTH - 161, 49], shade=True, padding=7), Spacer(1, 16)]
    story += [p('Watch together', 17, GREEN, True), Spacer(1, 6),
              p('Let the player describe a decision before offering advice. Choose one of the key actions, '
                'ask what they saw, and agree on one thing to try next time. Keep practice short and enjoyable.', 10)]

    # Appendix: source-level precision belongs here, not throughout the main report.
    story += [PageBreak()] + section('A', 'Evidence & method', 'The detail behind the report, kept together for checking and follow-up.')
    story += [p('How the score is calculated', 16, GREEN, True), Spacer(1, 7), p(safe(score['method']), 9),
              Spacer(1, 7), p(f'{score["unique_events"]} distinct actions support {score["rated_skills"]} grades. '
                  f'{score["rated_skills"]}/{score["total_skills"]} skills rated; weighted coverage {score["weighted_coverage_pct"]:g}%.', 9),
              Spacer(1, 9), p(safe(pub['stats_definitions']), 9), Spacer(1, 9),
              p(safe(pub['review']['analysis_status'] + '. ' + pub['review']['human_status'] + '.'), 9), Spacer(1, 17),
              p('Key action references', 16, GREEN, True), Spacer(1, 7)]
    from urllib.parse import quote
    for a in actions:
        url = 'https://scoutmeplay.com/report/' + quote(str(report.get('id') or ''), safe='') + '#event-' + quote(a['event_id'], safe='')
        bracket = a.get('contact_interval_ms')
        contact = f' Contact window {bracket[0]/1000:.3f}-{bracket[1]/1000:.3f} s; foot side unresolved.' if bracket else ''
        story.append(KeepTogether([p(f'<b>{safe(a["timestamp"])} / {safe(a["title"])}</b>{contact}', 9),
            p(f'{safe(a["event_id"])} / <link href="{url}" color="#12402A">Open video evidence</link>', 8, MUTED), Spacer(1, 7)]))
    story += [p('Links open the report and may require account access. Video times refer to the submitted clip.', 8, MUTED), Spacer(1, 16),
              p('Skill grades and their evidence', 16, GREEN, True), Spacer(1, 8)]
    skill_rows = [[p('SKILL / GRADE', 8, GREEN, True), p('SUPPORTING ACTION', 8, GREEN, True)]]
    for cat in CATEGORIES:
        for key in EXPECTED_SKILLS[cat]:
            sk = full.get(cat, {}).get(key) or {}
            if sk.get('cannot_evaluate') or not isinstance(sk.get('score'), (int, float)):
                continue
            refs = ', '.join(ev['event_id'] for ev in sk.get('evidence') or [])
            skill_rows.append([p(f'{safe(skill_label(key))} / {sk["score"]:.1f}', 8.5), p(safe(refs), 8, MUTED)])
    evidence_table = table(skill_rows, [180, WIDTH - 180], padding=3)
    evidence_table.repeatRows = 1
    story += [evidence_table, Spacer(1, 15), CondPageBreak(80),
              p('COMPLETE ACTION TIMELINE', 16, GREEN, True), Spacer(1, 9)]
    for row in pub['view']['actionTimeline']:
        story.append(KeepTogether([p(f'<b>{safe(row["timestamp"])} / {safe(row["title"])}</b>', 9, GREEN),
            p(safe(row['description']), 8.3, leading=11), p(safe(row['eventId']), 7.5, MUTED), Spacer(1, 8)]))
    story += [Spacer(1, 8), p(safe(pub['assessment_note']), 8.5, MUTED)]

    def page_frame(c, doc):
        c.saveState()
        c.setFillColor(GREEN)
        c.setFont(DISPLAY, 10)
        c.drawString(MARGIN, PAGE_H - 27, 'SCOUTMEPLAY')
        c.setFont(BODY, 7.5)
        c.setFillColor(MUTED)
        c.drawRightString(PAGE_W - MARGIN, PAGE_H - 27, pub['date'])
        c.setStrokeColor(LINE)
        c.line(MARGIN, 31, PAGE_W - MARGIN, 31)
        c.setFont(BODY, 7.5)
        c.drawString(MARGIN, 19, name + ' / Player report')
        c.drawRightString(PAGE_W - MARGIN, 19, str(doc.page))
        c.restoreState()

    doc = SimpleDocTemplate(str(output_path), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=49, bottomMargin=45, title=f'ScoutMePlay - {name}', author='ScoutMePlay',
        allowSplitting=1)
    doc.build(story, onFirstPage=page_frame, onLaterPages=page_frame)
