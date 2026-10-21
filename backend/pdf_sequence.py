"""Grouped Sequence report using the original Premium V2 card design."""
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak,
    KeepTogether, CondPageBreak, Flowable,
)
from pdf_v2 import (
    CREAM, BORDER, FOREST, BODY as BODY_COLOR, MUTED, SOFT, LIME,
    F_BODY, F_BOLD, F_BLACK, card, card_title, draw_par, _style,
    _header, _mini_header, _page_bg, _page_footer, _hero_card,
    _parent_summary_card, _overall_score_card, _match_stats_card,
    _age_comparison_card, derive_v2,
)

PAGE_W, PAGE_H = A4
MARGIN = 26
WIDTH = PAGE_W - 2 * MARGIN
GREEN, INK, LINE, PALE = FOREST, BODY_COLOR, BORDER, SOFT
BODY, BOLD, DISPLAY = F_BODY, F_BOLD, F_BLACK
pdfmetrics.registerFontFamily(BODY, normal=BODY, bold=BOLD, italic=BODY, boldItalic=BOLD)


class CardTable(Table):
    """The original white rounded cards, with measured content and intact corners."""
    def draw(self):
        c = self.canv
        c.saveState()
        card(c, 0, 0, self._width, self._height)
        clip = c.beginPath()
        clip.roundRect(0, 0, self._width, self._height, 9)
        c.clipPath(clip, stroke=0, fill=0)
        super().draw()
        c.restoreState()


class SectionBanner(Flowable):
    def __init__(self, number, title, deck):
        super().__init__()
        self.width, self.height = WIDTH, 50
        self.number, self.title, self.deck = number, title, deck

    def draw(self):
        c = self.canv
        card(c, 0, 0, self.width, self.height, fill=FOREST, stroke=FOREST)
        draw_par(c, safe(self.title.upper()), 12, 37, self.width - 24,
                 _style(F_BLACK, 13, LIME, leading=16))
        draw_par(c, safe(self.deck), 12, 17, self.width - 24,
                 _style(F_BODY, 7.8, colors.HexColor('#E9EFE2'), leading=10))


class CardHeading(Flowable):
    def __init__(self, title, width):
        super().__init__()
        self.title, self.width, self.height = title, width, 25

    def draw(self):
        card_title(self.canv, 0, 25, self.title, self.width)


class ClassicOverview(Flowable):
    """Keep the established profile / summary / donut, then stats / academy grid."""
    def __init__(self, report, resolve):
        super().__init__()
        self.width, self.height = WIDTH, 594
        self.report, self.resolve = report, resolve

    def draw(self):
        report, c = self.report, self.canv
        d, profile = derive_v2(report), report.get('player_details') or {}
        actions = report['report_publication']['key_actions']
        comments = {e['event_id']: e for e in report['full_report'].get('video_comments', [])}
        cover = next((e for e in actions if e['title'] == 'Goal' and action_image(e, comments, self.resolve)), None)
        cover = cover or next((e for e in actions if action_image(e, comments, self.resolve)), None)
        photo = action_image(cover, comments, self.resolve) if cover else None
        h1, gap, left, middle = 270, 9, 158, 205
        right = WIDTH - left - middle - 2 * gap
        y = self.height - h1
        _hero_card(c, d, profile, 0, y, left, h1, photo, contain_photo=True)
        _parent_summary_card(c, d['parentSummary'], left + gap, y, middle, h1)
        score = report['report_publication']['score']
        context = {'line': f'Provisional clip score. {score["rated_skills"]}/{score["total_skills"]} skills rated; '
                   f'{score["weighted_coverage_pct"]:g}% rubric coverage. Full-match level is not assessed.'}
        _overall_score_card(c, d, left + middle + 2 * gap, y, right, h1, ctx=context)
        h2, row_top, half = 230, y - gap, (WIDTH - gap) / 2
        _match_stats_card(c, d['matchStats'], 0, row_top - h2, half, h2,
                         'Counts describe this clip. Actions are segments, not individual ball touches.')
        _age_comparison_card(c, d['ageComparison'], d['ageBracket'], half + gap, row_top - h2, half, h2, rubric=True)
        note_y = row_top - h2 - gap - 50
        card(c, 0, note_y, WIDTH, 50, fill=SOFT)
        draw_par(c, 'Key actions, all four skill categories and development priorities follow together. '
                 'Precise timings and the complete evidence log are in the appendix.',
                 12, note_y + 38, WIDTH - 24, _style(F_BODY, 9, BODY_COLOR, leading=12))


class NumberedCanvas(rl_canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._page_states = []

    def showPage(self):
        self._page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._page_states)
        for state in self._page_states:
            self.__dict__.update(state)
            _page_footer(self, self._pageNumber, total)
            super().showPage()
        super().save()


def p(text, size=10, color=INK, bold=False, leading=None):
    return Paragraph(str(text), ParagraphStyle(
        'copy', fontName=BOLD if bold else BODY, fontSize=size, textColor=color,
        leading=leading or size * 1.42, spaceAfter=0,
    ))


def safe(text):
    return escape(str(text or ''))


def section(number, title, deck):
    return [SectionBanner(number, title, deck), Spacer(1, 12)]


def table(data, widths, *, shade=False, padding=10):
    t = CardTable(data, colWidths=widths, hAlign='LEFT')
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
    rows = [[CardHeading(label, (WIDTH - 16) / 2 - 66), p('GRADE', 8, MUTED, True)]]
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

    # Preserve the original Premium V2 cover grid and its existing card renderers.
    story.append(ClassicOverview(report, resolve))

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
                content = action_card(action, index, comments, resolve, col_width - 20, 300 if compact else 407)
                cards.append(table([[content]], [col_width], padding=10))
                widths.append(col_width)
            grid = Table([cards], colWidths=widths)
            grid.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]))
            story += [KeepTogether(grid), Spacer(1, 17)]
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
        content = [CardHeading(f'{i:02d} / {priority["name"]}', WIDTH - 24),
            p(safe(priority['issue']), 10), Spacer(1, 5), p('<b>Try this:</b> ' + safe(priority['how_to_improve']), 10)]
        story += [KeepTogether(table([[content]], [WIDTH], padding=12)), Spacer(1, 9)]
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
        _page_bg(c)
        if doc.page == 1:
            _header(c, pub['date'])
        else:
            _mini_header(c, name)
        c.restoreState()

    doc = BaseDocTemplate(str(output_path), pagesize=A4, title=f'ScoutMePlay - {name}', author='ScoutMePlay')
    def frame(top):
        return Frame(MARGIN, 34, WIDTH, PAGE_H - top - 34,
                     leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate('Cover', frames=[frame(80)], onPage=page_frame, autoNextPageTemplate='Body'),
        PageTemplate('Body', frames=[frame(58)], onPage=page_frame),
    ])
    doc.build(story, canvasmaker=NumberedCanvas)
