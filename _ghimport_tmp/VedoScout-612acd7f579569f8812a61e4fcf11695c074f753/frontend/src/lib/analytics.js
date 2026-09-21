// analytics.js — first-party, cookie-less analytics (GDPR-light).
// Anonymous session id lives in sessionStorage (dies with the browser tab
// session). No cookies, no IPs, no third parties. Admin pages are skipped.
const API = process.env.REACT_APP_BACKEND_URL;

let queue = [];
let flushTimer = null;
let currentPath = null;
let pageEnteredAt = Date.now();
let maxScroll = 0;
let utmSent = false;
let initialised = false;
let lastClick = { name: null, at: 0 };

const getSid = () => {
  try {
    let sid = sessionStorage.getItem("smp_sid");
    if (!sid) {
      sid = Array.from(crypto.getRandomValues(new Uint8Array(12)))
        .map((b) => b.toString(16).padStart(2, "0")).join("");
      sessionStorage.setItem("smp_sid", sid);
    }
    return sid;
  } catch (_) {
    return "nosession0000";
  }
};

const device = () => (/Mobi|Android|iPhone|iPad/i.test(navigator.userAgent) ? "mobile" : "desktop");

const utmOnce = () => {
  if (utmSent) return undefined;
  try {
    if (sessionStorage.getItem("smp_utm_sent")) { utmSent = true; return undefined; }
    const q = new URLSearchParams(window.location.search);
    const utm = {};
    ["source", "medium", "campaign", "content"].forEach((k) => {
      const v = q.get(`utm_${k}`);
      if (v) utm[k] = v;
    });
    if (!utm.source && q.get("fbclid")) utm.source = "facebook-click";
    utmSent = true;
    sessionStorage.setItem("smp_utm_sent", "1");
    return Object.keys(utm).length ? utm : undefined;
  } catch (_) {
    utmSent = true;
    return undefined;
  }
};

const scheduleFlush = () => {
  if (flushTimer) return;
  flushTimer = setTimeout(() => { flushTimer = null; flush(); }, 8000);
};

const flush = (useBeacon = false) => {
  if (!queue.length) return;
  const payload = JSON.stringify({ sid: getSid(), device: device(), events: queue.splice(0, 25) });
  try {
    if (useBeacon && navigator.sendBeacon) {
      navigator.sendBeacon(`${API}/api/track`, new Blob([payload], { type: "application/json" }));
    } else {
      fetch(`${API}/api/track`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: payload, keepalive: true,
      }).catch(() => {});
    }
  } catch (_) { /* analytics must never break the app */ }
};

const push = (event) => {
  if ((event.path || "").startsWith("/admin")) return;
  queue.push(event);
  if (queue.length >= 20) flush();
  else scheduleFlush();
};

const leaveEvent = () => ({
  type: "leave",
  path: currentPath || window.location.pathname,
  seconds: (Date.now() - pageEnteredAt) / 1000,
  scroll: Math.round(maxScroll),
});

export const trackFunnel = (name) => {
  push({ type: "funnel", name, path: currentPath || window.location.pathname });
};

export const analyticsPageView = (path) => {
  if (currentPath !== null && currentPath !== path) push(leaveEvent());
  currentPath = path;
  pageEnteredAt = Date.now();
  maxScroll = 0;
  push({
    type: "pageview",
    path,
    referrer: (document.referrer || "").slice(0, 200) || undefined,
    utm: utmOnce(),
  });
};

export const initAnalytics = () => {
  if (initialised) return;
  initialised = true;

  window.addEventListener("scroll", () => {
    const h = document.documentElement.scrollHeight - window.innerHeight;
    if (h > 0) maxScroll = Math.max(maxScroll, Math.min(100, ((window.scrollY || 0) / h) * 100));
  }, { passive: true });

  // CTA clicks — only elements that carry a data-testid (intentional UI)
  document.addEventListener("click", (e) => {
    const el = e.target && e.target.closest && e.target.closest("button[data-testid], a[data-testid], [role='button'][data-testid]");
    if (!el) return;
    const name = el.getAttribute("data-testid");
    const now = Date.now();
    if (!name || (lastClick.name === name && now - lastClick.at < 1000)) return;
    lastClick = { name, at: now };
    push({ type: "click", name, path: currentPath || window.location.pathname });
  }, { capture: true, passive: true });

  const onHide = () => {
    if (currentPath !== null) queue.push(leaveEvent());
    flush(true);
  };
  window.addEventListener("pagehide", onHide);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") onHide();
  });
};
