// Derivation layer for the pixel-perfect Premium Report V2.
// Maps the existing full_report JSON (+ new presentation fields) into the
// exact data shapes the V2 sections render. NEVER touches scores or logic —
// pure read-only mapping with graceful fallbacks for missing fields.

// FIX 01 — authority-aware frame lookup lives in a pure, testable module.
import { buildFrameLookup, isAuthorityReport, canUseAuthorityProof, resolveAuthorityFrame, selectEvidenceHighlight } from "../../lib/authorityJoin.mjs";

export const SKILL_LABELS = {
  first_touch: "First Touch", ball_control: "Ball Control", dribbling: "Dribbling",
  passing: "Passing", shooting: "Shooting", weak_foot: "Weak Foot", one_v_one: "1v1 Attacking",
  positioning: "Positioning", off_ball_movement: "Off-Ball Movement", scanning: "Scanning",
  decision_making: "Decision Making", timing_of_runs: "Timing of Runs", game_understanding: "Game Understanding",
  acceleration: "Acceleration", speed: "Speed", balance: "Balance", agility: "Agility",
  intensity: "Intensity", body_control: "Body Control",
  confidence: "Confidence", work_rate: "Work Rate", courage_in_duels: "Courage in Duels",
  response_to_mistakes: "Response to Mistakes", competitive_mindset: "Competitive Drive", focus: "Focus",
};

const TIER_PERCENTILE = {
  elite_academy: { label: "Top 10%", width: 90 },
  pro_academy: { label: "Top 20%", width: 80 },
  strong_club: { label: "Top 40%", width: 60 },
  standard_club: { label: "Top 60%", width: 40 },
};

const TIER_DOTS = { standard_club: 2, strong_club: 3, pro_academy: 4, elite_academy: 5 };
const TIER_LABELS = { standard_club: "Grassroots Club", strong_club: "Strong Club", pro_academy: "Strong Academy", elite_academy: "Elite Academy" };
const NEXT_TIER = { standard_club: "strong_club", strong_club: "pro_academy", pro_academy: "elite_academy", elite_academy: "elite_academy" };

const POSITION_ABBR = {
  Goalkeeper: "GK", "Centre-back": "CB", "Full-back": "FB", "Wing-back": "WB",
  "Defensive Midfielder": "DM", "Central Midfielder": "CM", "Attacking Midfielder": "AM",
  Winger: "LW / RW", Striker: "ST",
};

export function tsToSeconds(ts) {
  if (!ts || typeof ts !== "string" || !ts.includes(":")) return null;
  const [m, s] = ts.split(":").map((x) => parseInt(x, 10));
  if (Number.isNaN(m) || Number.isNaN(s)) return null;
  return m * 60 + s;
}

function firstSentences(text, max = 160) {
  if (!text) return "";
  const clean = String(text).trim();
  if (clean.length <= max) return clean;
  const cut = clean.slice(0, max);
  const lastDot = cut.lastIndexOf(". ");
  if (lastDot > 40) return cut.slice(0, lastDot + 1);
  // Never cut mid-sentence: if no boundary fits, show the whole first sentence.
  const end = clean.indexOf(". ");
  return end > 0 ? clean.slice(0, end + 1) : clean;
}

function collectSkills(full) {
  const out = [];
  for (const cat of ["technical", "tactical", "physical", "mentality"]) {
    const sec = full?.[cat] || {};
    for (const [key, sk] of Object.entries(sec)) {
      if (!sk || typeof sk !== "object") continue;
      if (sk.cannot_evaluate || typeof sk.score !== "number") continue;
      out.push({
        key, category: cat,
        label: SKILL_LABELS[key] || key.replace(/_/g, " "),
        score: sk.score,
        notes: sk.notes || "",
        confidence: String(sk.confidence || "").toLowerCase(),
        tier: String(sk.tier_for_age || "").toLowerCase(),
        evidence: Array.isArray(sk.evidence) ? sk.evidence : [],
        verdict: sk.verdict || "",
      });
    }
  }
  return out;
}

export function deriveV2(report) {
  const full = report?.full_report || {};
  const pd = report?.player_details || {};
  const authority = isAuthorityReport(full);
  const skills = collectSkills(full);
  const frames = buildFrameLookup(full?.video_comments, authority);
  const scoutView = full.scout_view || {};
  const pa = full.potential_assessment || {};
  const ob = full.overall_benchmark || {};
  const obTier = String(ob.tier || "").toLowerCase();

  // ---- Top strengths (4 highest observed skills) ----
  // Each card prefers an evidence moment not already used by another card,
  // so the four proofs show four different moments when the footage allows.
  const confRank = { high: 2, medium: 1, low: 0 };
  const usedTs = new Set();
  const topStrengths = [...skills]
    .sort((a, b) => b.score - a.score || (confRank[b.confidence] ?? 0) - (confRank[a.confidence] ?? 0))
    .slice(0, 4)
    .map((s) => {
      const evs = (s.evidence || []).filter((e) => e && e.timestamp && e.timestamp !== "General");
      const ev = evs.find((e) => !usedTs.has(e.timestamp)) || evs[0];
      if (ev?.timestamp) usedTs.add(ev.timestamp);
      // FIX 01 — authority reports join by IDs (exact only); legacy keeps ts.
      const fr = frames.find(ev?.timestamp, { evidenceId: ev?.evidence_id, eventId: ev?.event_id });
      return {
        name: s.label, score: s.score, category: s.category,
        note: s.notes,
        timestamp: fr?.ts || ev?.timestamp || null,
        thumb: fr?.url || null,
        thumbVerified: !!fr?.verified,
        evidenceId: ev?.evidence_id || null,
        eventId: ev?.event_id || null,
        proofable: canUseAuthorityProof(authority, ev),
      };
    });

  // ---- Development priorities ----
  let devPriorities = Array.isArray(full.development_priorities_detailed) && full.development_priorities_detailed.length
    ? full.development_priorities_detailed.slice(0, 3).map((p) => ({
        name: p.name, score: typeof p.score === "number" ? p.score : null,
        issue: p.issue || "", howTo: p.how_to_improve || "",
      }))
    : [...skills].sort((a, b) => a.score - b.score).slice(0, 3).map((s) => ({
        name: s.label, score: s.score,
        issue: s.notes,
        howTo: (s.verdict.split("focus on")[1] || s.verdict).trim(),
      }));

  // ---- Age comparison (6 skills, best percentile first) ----
  const ageComparison = [...skills]
    .filter((s) => TIER_PERCENTILE[s.tier])
    .sort((a, b) => (TIER_PERCENTILE[b.tier]?.width ?? 0) - (TIER_PERCENTILE[a.tier]?.width ?? 0) || b.score - a.score)
    .slice(0, 6)
    .map((s) => ({ name: s.label, ...TIER_PERCENTILE[s.tier] }));

  // ---- Snapshot ----
  const snap = full.snapshot || {};
  const snapshot = {
    biggestStrength: snap.biggest_strength || firstSentences(scoutView.key_strengths?.[0], 45) || "—",
    developmentArea: snap.biggest_development_area || firstSentences(scoutView.development_priorities?.[0], 45) || "—",
    hiddenTalent: snap.hidden_talent || firstSentences(scoutView.key_strengths?.slice(-1)[0], 45) || "—",
    progressNote: snap.overall_progress_note || "On the right track!",
  };

  // ---- Snapshot moments (photo cards: real frame + timestamp + annotation) ----
  const snapEvents = (Array.isArray(full.action_timeline) ? full.action_timeline : [])
    .filter((a) => a && a.timestamp && (a.title || a.description)
      && String(a.identity_confidence || "").toLowerCase() !== "low");
  const snapFrameEntries = (full.video_comments || [])
    .filter((c) => c && c.frame_url && !c.frame_placeholder && c.timestamp
      && (authority ? c.proof_frame_verified === true : c.identity_verified !== false))
    .map((c) => ({ sec: tsToSeconds(c.timestamp), ts: c.timestamp, url: c.frame_url, comment: c.comment || "",
      evidenceId: c.evidence_id || null, eventId: c.event_id || null }));
  const snapUsedFrames = new Set();
  const snapCloseFrame = (ev) => {
    // FIX 01 — authority reports: EXACT event_id join only (no nearest <=8s).
    if (authority) {
      const best = snapFrameEntries.find(
        (e) => !snapUsedFrames.has(e.url) && ev?.event_id && e.eventId === ev.event_id) || null;
      if (best) snapUsedFrames.add(best.url);
      return best;
    }
    const ts = ev?.timestamp;
    const sec = tsToSeconds(ts);
    let best = null;
    for (const e of snapFrameEntries) {
      if (snapUsedFrames.has(e.url)) continue;
      if (ts && e.ts === ts) { best = e; break; }
      if (sec != null && e.sec != null) {
        const d = Math.abs(e.sec - sec);
        if (d <= 8 && (!best || d < Math.abs(best.sec - sec))) best = e;
      }
    }
    if (best) snapUsedFrames.add(best.url);
    return best || null;
  };
  // Frame-first fallback: every snapshot card must show a REAL verified frame.
  // LEGACY ONLY — authority reports never display an unrelated moment: no
  // exact bound proof means no photo for that card.
  const takeAnyFrame = () => {
    if (authority) return null;
    const e = snapFrameEntries.find((x) => !snapUsedFrames.has(x.url)) || null;
    if (e) snapUsedFrames.add(e.url);
    return e;
  };
  const snapTokens = (s) => String(s || "").toLowerCase().split(/[^a-z]+/).filter((w) => w.length > 3);
  const snapTokMatch = (a, b) => a.startsWith(b.slice(0, 4)) || b.startsWith(a.slice(0, 4));
  const snapUsedEv = new Set();
  const snapMatchEvent = (text, pref) => {
    const want = snapTokens(text);
    let best = null;
    let bestScore = 0;
    for (const e of snapEvents) {
      if (snapUsedEv.has(e)) continue;
      const r = String(e.rating || "").toLowerCase();
      if (pref === "positive" && r === "negative") continue;
      if (pref === "issue" && r === "positive") continue;
      let sc = pref === "issue" && r === "neutral" ? 0.25 : 0;
      const have = snapTokens(`${e.title} ${e.description} ${e.action_type}`);
      for (const w of have) if (want.some((t) => snapTokMatch(w, t))) sc += 1;
      const oc = String(e.outcome || "").toLowerCase();
      if (pref === "positive" && (oc === "goal" || oc === "assist")) sc += 0.5;
      if (sc > bestScore) { best = e; bestScore = sc; }
    }
    if (best) snapUsedEv.add(best);
    return best;
  };
  const SNAP_ANNOT_BY_TYPE = {
    dribble: "path", pass: "arrow", shot: "arrow", off_ball_run: "run",
    duel: "circle", defensive_action: "run", first_touch: "circle",
  };
  const buildSnapMoment = (key, text, pref, forcedAnnot, preferEventTitle = false) => {
    const ev = snapMatchEvent(text, pref);
    let fr = ev ? snapCloseFrame(ev) : null;
    let frComment = null;
    if (!fr) {
      fr = takeAnyFrame();
      frComment = fr?.comment || null;
    }
    const phrase = firstSentences(text, 60);
    const evTitle = firstSentences(ev?.title, 60);
    const fcTitle = firstSentences(frComment, 60);
    const title = (preferEventTitle ? evTitle || fcTitle || phrase : phrase || evTitle || fcTitle) || "—";
    // Caption always describes the moment in the photo: the matched event's
    // description, or the scout's verified comment for the fallback frame.
    let desc = firstSentences(ev?.description || frComment || (preferEventTitle ? "" : text), 220);
    if (desc === title) desc = "";
    return {
      key,
      title,
      desc,
      timestamp: fr?.ts || ev?.timestamp || null,
      thumb: fr?.url || null,
      annot: forcedAnnot || SNAP_ANNOT_BY_TYPE[String(ev?.action_type || "").toLowerCase()] || "circle",
      glance: null,
    };
  };
  const explicitMoments = Array.isArray(full.snapshot_moments) && full.snapshot_moments.length >= 4
    ? full.snapshot_moments.slice(0, 4).map((x) => {
        // FIX 01 C01 — authority: the photo must come from the exactly bound
        // evidence object; x.frame_url is never trusted as authority evidence.
        const bound = authority ? resolveAuthorityFrame(full.video_comments, x) : null;
        return {
          key: x.key,
          title: x.title || "—",
          desc: x.desc || "—",
          timestamp: x.timestamp || null,
          thumb: authority ? (bound?.frame_url || null) : (x.frame_url || null),
          annot: x.annot || "circle",
          glance: x.glance || null,
          evidenceId: x.evidence_id || null,
          eventId: x.event_id || null,
        };
      })
    : null;
  const snapshotMoments = explicitMoments || [
    buildSnapMoment("strength", snapshot.biggestStrength, "positive", null),
    buildSnapMoment("noticed", snap.scout_discovery || "scanning awareness vision decision space between the lines", "positive", "scan", !snap.scout_discovery),
    buildSnapMoment("hidden", snapshot.hiddenTalent, "positive", "run"),
    buildSnapMoment("develop", snapshot.developmentArea, "issue", "circle"),
  ];

  // ---- Roadmap ----
  const rm = full.development_roadmap || {};
  const roadmap = [
    { key: "NOW", text: rm.now || "Build confidence and technical foundation" },
    { key: "3 MONTHS", text: rm.three_months || firstSentences(pa.three_month_focus, 60) || "Sharpen the main development area" },
    { key: "6 MONTHS", text: rm.six_months || firstSentences(ob.what_separates_from_next_tier, 60) || "Close the gap to the next level" },
    { key: "12 MONTHS", text: rm.twelve_months || firstSentences(pa.recommended_next_step, 60) || "High impact in matches" },
  ];

  // ---- Training week (map plan exercises onto days) ----
  const exercises = full.training_plan?.exercises || [];
  const trainingWeek = [
    { day: "MON", name: exercises[0]?.name || "Technical work", mins: exercises[0]?.duration || "" },
    { day: "WED", name: exercises[1]?.name || "Skill drills", mins: exercises[1]?.duration || "" },
    { day: "FRI", name: exercises[2]?.name || "Game moves", mins: exercises[2]?.duration || "" },
    { day: "WEEKEND", name: exercises[3]?.name || "Match Challenge", mins: exercises[3]?.duration || "" },
  ];

  // ---- Parent summary / tips / coach notes ----
  const ps = full.parent_summary || {};
  const parentSummary = {
    headline: ps.headline || firstSentences(full.executive_summary, 110),
    paragraphs: Array.isArray(ps.paragraphs) && ps.paragraphs.length
      ? ps.paragraphs.slice(0, 2)
      : [firstSentences(full.executive_summary, 260), firstSentences(full.final_summary, 260)].filter(Boolean),
    goodNews: ps.good_news || firstSentences(pa.development_potential, 220),
  };
  const parentTips = Array.isArray(full.parent_tips) && full.parent_tips.length
    ? full.parent_tips.slice(0, 4)
    : [
        "Praise effort and brave decisions, not just goals.",
        "Encourage trying new skills in games.",
        "Support training, rest and healthy habits.",
        "Be the biggest fan and enjoy the journey together!",
      ];
  const coachNotes = Array.isArray(full.coach_notes) && full.coach_notes.length
    ? full.coach_notes.slice(0, 6)
    : [
        ...(scoutView.development_priorities || []).slice(0, 3),
        scoutView.positional_suitability ? `Perfect role: ${scoutView.positional_suitability}` : null,
        pa.three_month_focus ? `Focus in training: ${firstSentences(pa.three_month_focus, 90)}` : null,
      ].filter(Boolean);

  // ---- Scout outlook ----
  const so = full.scout_outlook || {};
  const nextTier = NEXT_TIER[obTier] || obTier;
  const scoutOutlook = {
    currentLabel: so.current_level_label || ob.tier_label || TIER_LABELS[obTier] || "—",
    currentDots: so.current_level_dots || TIER_DOTS[obTier] || 3,
    potentialLabel: so.potential_level_label || TIER_LABELS[nextTier] || "—",
    potentialDots: so.potential_level_dots || Math.min(5, (TIER_DOTS[obTier] || 3) + 1),
    readiness: so.recruitment_readiness || (obTier === "elite_academy" ? "High — Trial Ready" : obTier === "pro_academy" ? "Medium — Keep Developing" : "Early — Keep Building"),
    longTerm: so.long_term_potential || (/very high|high/i.test(pa.development_potential || "") ? "High" : "Medium"),
    longTermNote: so.long_term_note || firstSentences(pa.development_potential, 140),
  };

  // ---- Match stats ----
  const ms = full.match_stats || null;
  const matchStats = ms ? [
    { label: "Total Actions", value: ms.total_actions, pct: Math.min(100, ((ms.total_actions || 0) / 80) * 100) },
    { label: "Successful Dribbles", value: ms.successful_dribbles, pct: Math.min(100, ((ms.successful_dribbles || 0) / 12) * 100) },
    { label: "Key Passes", value: ms.key_passes, pct: Math.min(100, ((ms.key_passes || 0) / 8) * 100) },
    { label: "Shots", value: ms.shots, pct: Math.min(100, ((ms.shots || 0) / 8) * 100) },
    { label: "Duels Won", value: ms.duels_won, pct: (() => { const m = String(ms.duels_won || "").match(/(\d+)\s*\/\s*(\d+)/); return m && +m[2] > 0 ? (+m[1] / +m[2]) * 100 : 50; })() },
    { label: "Minutes Analysed", value: `${ms.minutes_analysed ?? "—"}'`, pct: Math.min(100, ((ms.minutes_analysed || 0) / 90) * 100) },
  ].filter((r) => r.value !== undefined && r.value !== null) : null;

  // ---- Video highlight (authority: fail-closed proof_verified only) ----
  const vcBest = selectEvidenceHighlight(full.video_comments, authority);
  const videoHighlight = vcBest
    ? {
        timestamp: vcBest.timestamp, caption: vcBest.comment,
        // FIX 02 — authority: the highlight photo/badge must satisfy the
        // fail-closed proof-frame state; never "verified" by implication.
        thumb: authority
          ? (vcBest.proof_frame_verified === true ? vcBest.frame_url || null : null)
          : (vcBest.identity_verified === false ? null : vcBest.frame_url || null),
        thumbVerified: authority ? vcBest.proof_frame_verified === true : vcBest.identity_verified === true,
        evidenceId: vcBest.evidence_id || null,
      }
    : null;

  // ---- Overall gauge ----
  const overall = typeof full.scores?.overall_development === "number" ? full.scores.overall_development : null;
  const ageBracket = ob.age_bracket_used || null;

  // ---- Action timeline (chronological match report) ----
  const actionTimeline = (Array.isArray(full.action_timeline) ? full.action_timeline : [])
    .filter((a) => a && a.timestamp && (a.title || a.description)
      && String(a.identity_confidence || "").toLowerCase() !== "low")
    .slice(0, 15)
    .map((a) => {
      const oc = String(a.outcome || "").toLowerCase();
      return {
        timestamp: a.timestamp,
        title: a.title || String(a.action_type || "").replace(/_/g, " "),
        description: firstSentences(a.description, 110),
        rating: typeof a.rating === "number" ? a.rating : null,
        outcome: ["positive", "neutral", "negative"].includes(oc) ? oc : "neutral",
        tracked: !!a.tracking_verified,
        eventId: a.event_id || null,
        // FIX 02 — fail-closed proof state; authority rows without it are
        // rendered non-clickable (defense-in-depth, backend already drops them).
        proofVerified: a.proof_verified === true,
        proofable: canUseAuthorityProof(authority, a),
      };
    });

  // ---- Parents package (home drills / watch together / letter) ----
  const pp = full.parents_package || null;
  const homeDrills = (Array.isArray(pp?.home_drills) ? pp.home_drills : [])
    .filter((x) => x && x.name && Array.isArray(x.steps)).slice(0, 3);
  const watchTogether = pp?.watch_together && Array.isArray(pp.watch_together.moments)
    ? pp.watch_together : null;
  const playerMessage = pp?.message_to_player?.body ? pp.message_to_player : null;
  const parentsPackage = (homeDrills.length || watchTogether || playerMessage)
    ? { homeDrills, watchTogether, playerMessage, authority }
    : null;

  // ---- Next match missions (printable card) ----
  const missions = (Array.isArray(full.next_match_missions) ? full.next_match_missions : [])
    .filter((m) => m && m.mission).slice(0, 3);

  // ---- Parent value metrics (Stage 4 — involvement / bravery / reaction / off-ball / top minutes) ----
  const pvmRaw = full.parent_value_metrics;
  let parentMetrics = null;
  if (pvmRaw && typeof pvmRaw === "object") {
    const topMinutes = (Array.isArray(pvmRaw.top_minutes) ? pvmRaw.top_minutes : [])
      .filter((m) => m && m.from).slice(0, 3);
    const pm = {
      involvement: pvmRaw.involvement || null,
      bravery: pvmRaw.bravery || null,
      reaction: pvmRaw.reaction_after_mistake || null,
      offBall: pvmRaw.off_ball_work || null,
      topMinutes,
      authority,
    };
    if (pm.involvement || pm.bravery || pm.reaction || pm.offBall || topMinutes.length) parentMetrics = pm;
  }

  // ---- Grow Your Game (evidence-gated football education) ----
  const gygRaw = full.grow_your_game;
  const growYourGame = gygRaw && Array.isArray(gygRaw.lessons) && gygRaw.lessons.length
    ? { lessons: gygRaw.lessons, homework: Array.isArray(gygRaw.homework_plan) ? gygRaw.homework_plan : [], authority }
    : null;

  // ---- Parent corner (Layer 1: AI-personalized; Layer 2 lives client-side) ----
  const parentCorner = full.parent_corner && typeof full.parent_corner === "object" ? full.parent_corner : null;

  // ---- Evidence-integrity note (strict image policy) ----
  const ist = report?.identity_stats;
  const identityNote = ist && (ist.checked || 0) > 0 && (ist.verified || 0) / ist.checked < 0.5
    ? "Some moments are shown as text only — an image is displayed only when an independent identity check confirms your player with certainty."
    : null;

  // ---- Cross-verification (intelligent dual-pass trust signal) ----
  const cvRaw = full.cross_verification;
  const crossVerification = cvRaw && cvRaw.status === "verified" && (cvRaw.events_checked || 0) > 0
    ? { checked: cvRaw.events_checked, dropped: cvRaw.events_dropped || 0 }
    : null;

  return {
    playerType: full.player_type || "",
    authority,
    overall, ageBracket,
    stars: overall != null ? Math.round(overall / 2) : 0,
    positionAbbr: POSITION_ABBR[pd.position] || pd.position || "—",
    topStrengths, devPriorities, ageComparison, snapshot, snapshotMoments, roadmap,
    trainingWeek, parentSummary, parentTips, coachNotes, scoutOutlook,
    matchStats, videoHighlight, identityNote, actionTimeline, parentsPackage, missions,
    parentMetrics, growYourGame, parentCorner, crossVerification,
  };
}
