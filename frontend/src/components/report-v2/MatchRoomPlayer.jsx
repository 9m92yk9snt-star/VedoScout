import React, { useEffect, useMemo, useRef, useState, useId } from 'react';
import { Play, Pause, X, RotateCcw } from 'lucide-react';
import { roomFor, graphicsAt } from './matchRoomModel';
import './matchroom.css';
const clock = ms => `${String(Math.floor(ms / 60000)).padStart(2, '0')}:${String(Math.floor(ms / 1000) % 60).padStart(2, '0')}`;
export function MatchRoomPlayer({
  proof,
  videoUrl,
  posterUrl,
  skill,
  onClose
}) {
  const video = useRef(null),
    stage = useRef(null),
    programmatic = useRef(false),
    consumed = useRef(new Set()),
    last = useRef(null);
  const [failed, setFailed] = useState(false),
    [error, setError] = useState(false),
    [playing, setPlaying] = useState(false),
    [slow, setSlow] = useState(false),
    [at, setAt] = useState(0),
    [stop, setStop] = useState(null),
    [done, setDone] = useState(false),
    [ratio, setRatio] = useState(16 / 9);
  const [bounds, setBounds] = useState({
    left: 0,
    top: 0,
    width: '100%',
    height: '100%'
  });
  const clip = !!proof.clip && Number.isFinite(proof.clipStart) && !failed;
  const offset = clip ? proof.clipStart : 0;
  const raw = proof.comment;
  const fallback = finiteSeconds(proof.ts);
  const room = useMemo(() => roomFor(raw, fallback), [raw, fallback]);
  const from = Math.max(room.start, clip ? offset * 1000 : 0),
    until = clip && Number.isFinite(raw?.tele_clip_end) ? Math.min(room.end + 750, raw.tele_clip_end * 1000) : room.end + 750;
  const mark = graphicsAt(room, at),
    id = useId().replace(/:/g, '');
  const observation = (skill?.lines || []).filter(x => typeof x === 'string').join(' ') || raw?.comment || 'Review the documented action in your match.';
  useEffect(() => {
    const el = stage.current;
    if (!el) return undefined;
    const measure = () => {
      const w = el.clientWidth,
        h = el.clientHeight,
        fw = Math.min(w, h * ratio),
        fh = fw / ratio;
      setBounds({
        left: (w - fw) / 2,
        top: (h - fh) / 2,
        width: fw,
        height: fh
      });
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [ratio]);
  useEffect(() => {
    const v = video.current;
    if (!v) return undefined;
    let frame;
    const update = () => {
      const ms = (v.currentTime + (clip ? offset : 0)) * 1000;
      setAt(ms);
      if (!v.paused && !v.seeking) {
        const next = room.stops.find(s => !consumed.current.has(s.media_ms) && last.current != null && last.current < s.media_ms && ms >= s.media_ms);
        if (next) {
          consumed.current.add(next.media_ms);
          v.pause();
          programmatic.current = true;
          v.currentTime = Math.max(0, next.media_ms / 1000 - (clip ? offset : 0));
          setAt(next.media_ms);
          setStop(next);
        } else if (ms >= until) {
          v.pause();
          setDone(true);
        }
      }
      last.current = ms;
    };
    const tick = () => {
      update();
      frame = v.requestVideoFrameCallback(tick);
    };
    if (v.requestVideoFrameCallback) frame = v.requestVideoFrameCallback(tick);
    const seek = () => {
      const ms = (v.currentTime + (clip ? offset : 0)) * 1000;
      last.current = ms;
      if (programmatic.current) {
        programmatic.current = false;
        setAt(ms);
        return;
      }
      consumed.current = new Set(room.stops.filter(s => s.media_ms <= ms).map(s => s.media_ms));
      setStop(null);
      setDone(false);
      setAt(ms);
    };
    v.addEventListener('timeupdate', update);
    v.addEventListener('seeked', seek);
    return () => {
      if (frame != null) v.cancelVideoFrameCallback?.(frame);
      v.removeEventListener('timeupdate', update);
      v.removeEventListener('seeked', seek);
      v.pause();
    };
  }, [clip, offset, room, until]);
  const play = () => {
    const v = video.current;
    if (!v) return;
    setError(false);
    setStop(null);
    v.play().catch(() => setError(true));
  };
  const restart = () => {
    const v = video.current;
    if (!v) return;
    v.pause();
    v.currentTime = Math.max(0, from / 1000 - (clip ? offset : 0));
    consumed.current = new Set();
    last.current = from;
    setDone(false);
    setStop(null);
  };
  const initialize = () => {
    const v = video.current;
    if (!v) return;
    setRatio(v.videoWidth / v.videoHeight || 16 / 9);
    v.currentTime = Math.max(0, from / 1000 - (clip ? offset : 0));
    last.current = from;
    setAt(from);
    v.playbackRate = slow ? .5 : 1;
  };
  return <section className="smp-matchroom" aria-label="Match Room" data-testid="match-room">
    <header><div><span className="mr-kicker">MATCH ROOM · {skill?.label || 'YOUR MATCH'}</span><strong>{proof.playerName || 'Your match'}<span className="mr-time">{clock(at)}</span></strong></div><button type="button" onClick={onClose} aria-label="Close Match Room"><X size={18} /></button></header>
    <div className="mr-stage" ref={stage} style={{
      aspectRatio: ratio
    }}>
      <video ref={video} src={(clip ? proof.clip : videoUrl) || undefined} poster={posterUrl || undefined} playsInline preload="metadata" onLoadedMetadata={initialize} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => {
        setPlaying(false);
        setDone(true);
      }} onError={() => {
        if (clip && videoUrl) {
          setFailed(true);
          setStop(null);
          consumed.current = new Set();
          last.current = null;
        } else setError(true);
      }} data-testid="match-room-video" />
      {mark && <svg className="mr-graphics" style={bounds} viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-label="Observed positions at this source frame">
        <defs><radialGradient id={`ground-${id}`}><stop offset="0" stopColor="#d9fc77" stopOpacity=".5" /><stop offset="1" stopColor="#d9fc77" stopOpacity="0" /></radialGradient><marker id={`arrow-${id}`} markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto" viewBox="0 0 6 6"><path d="M0 0L6 3L0 6Z" fill="#d9fc77" /></marker></defs>
        {mark.ground && <ellipse cx={mark.ground[0] * 1000} cy={Math.min(1, mark.ground[1] + .012) * 1000} rx={mark.player_width * 700} ry={mark.player_width * 150} fill={`url(#ground-${id})`} />}
        {mark.groundTrail && <line x1={mark.groundTrail[0][0] * 1000} y1={Math.min(1,mark.groundTrail[0][1]+.025) * 1000} x2={mark.groundTrail[1][0] * 1000} y2={Math.min(1,mark.groundTrail[1][1]+.025) * 1000} stroke="#d9fc77" strokeWidth="2" strokeDasharray="4 3" markerEnd={`url(#arrow-${id})`} />}
        {mark.ballTrail && <line x1={mark.ballTrail[0][0] * 1000} y1={mark.ballTrail[0][1] * 1000} x2={mark.ballTrail[1][0] * 1000} y2={mark.ballTrail[1][1] * 1000} stroke="#d9fc77" strokeWidth="2" markerEnd={`url(#arrow-${id})`} />}
      </svg>}
      {stop && !done && <div className="mr-caption"><span className="mr-kicker">{skill?.label || stop.label} · {stop.phase === 'result' ? 'THE RESULT' : 'YOUR QUALITY'}</span><strong>{(stop.caption || observation).length > 170 ? (stop.caption || observation).slice(0, 167) + '…' : stop.caption || observation}</strong></div>}
    </div>
    <div className="mr-controls"><button type="button" onClick={() => {
        if (playing) video.current?.pause();else {
          if (done) restart();
          play();
        }
      }} aria-label={playing ? 'Pause' : 'Continue'}>{playing ? <Pause size={20} /> : <Play size={20} />}</button><div className="mr-progress"><div>{done ? 'Action complete' : stop ? 'Take a moment · continue when ready' : 'Your match · step by step'}</div><input className="mr-scrub" type="range" aria-label="Video position" min={from} max={Math.max(from + 1, until)} step="40" value={Math.max(from, Math.min(until, at))} onChange={e => {
          const v = video.current;
          if (v) {
            v.pause();
            v.currentTime = Number(e.target.value) / 1000 - (clip ? offset : 0);
          }
        }} /><div className="mr-stops">{room.stops.map(s => <span key={s.media_ms}>{s.label}</span>)}</div></div><button type="button" aria-pressed={slow} onClick={() => {
        const next = !slow;
        setSlow(next);
        if (video.current) video.current.playbackRate = next ? .5 : 1;
      }}>{slow ? '0.5×' : '1×'}</button></div>
    {error && <p role="alert">Video could not play. <button type="button" onClick={play}>Try again</button></p>}
    {done && <div className="mr-explanation" aria-live="polite"><span className="mr-kicker">WHAT TO TAKE FROM THIS</span><p>{observation}</p>{typeof skill?.next_level === 'string' && <p>{skill.next_level}</p>}<button type="button" onClick={restart}><RotateCcw size={16} /> Watch again</button></div>}
  </section>;
}
function finiteSeconds(ts) {
  if (typeof ts !== 'string') return 0;
  return ts.split(':').reduce((n, p) => n * 60 + (Number(p) || 0), 0);
}
