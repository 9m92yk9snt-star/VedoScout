// pixels.js — Meta (Facebook/Instagram) + TikTok pixel loader & event tracker.
// Pixels ONLY load when the visitor has accepted MARKETING cookies (GDPR).
// Pixel IDs are admin-configured via /api/settings/pixels.
import api from "@/lib/api";

const CONSENT_KEY = "smp_cookie_consent_v1";

const loaded = { meta: false, tiktok: false };
const ids = { meta: null, tiktok: null };
let fetched = false;
let listenerAttached = false;

const marketingAllowed = () => {
  try {
    const c = JSON.parse(localStorage.getItem(CONSENT_KEY) || "null");
    return !!c?.marketing;
  } catch {
    return false;
  }
};

/* eslint-disable */
function loadMeta(id) {
  if (!window.fbq) {
    (function (f, b, e, v, n, t, s) {
      if (f.fbq) return; n = f.fbq = function () { n.callMethod ? n.callMethod.apply(n, arguments) : n.queue.push(arguments); };
      if (!f._fbq) f._fbq = n; n.push = n; n.loaded = !0; n.version = "2.0"; n.queue = [];
      t = b.createElement(e); t.async = !0; t.src = v; s = b.getElementsByTagName(e)[0]; s.parentNode.insertBefore(t, s);
    })(window, document, "script", "https://connect.facebook.net/en_US/fbevents.js");
  }
  window.fbq("init", id);
  loaded.meta = true;
}

function loadTikTok(id) {
  if (!window.ttq) {
    (function (w, d, t) {
      w.TiktokAnalyticsObject = t; var ttq = (w[t] = w[t] || []);
      ttq.methods = ["page", "track", "identify", "instances", "debug", "on", "off", "once", "ready", "alias", "group", "enableCookie", "disableCookie"];
      ttq.setAndDefer = function (t, e) { t[e] = function () { t.push([e].concat(Array.prototype.slice.call(arguments, 0))); }; };
      for (var i = 0; i < ttq.methods.length; i++) ttq.setAndDefer(ttq, ttq.methods[i]);
      ttq.instance = function (t) { var e = ttq._i[t] || []; for (var n = 0; n < ttq.methods.length; n++) ttq.setAndDefer(e, ttq.methods[n]); return e; };
      ttq.load = function (e, n) {
        var i = "https://analytics.tiktok.com/i18n/pixel/events.js";
        ttq._i = ttq._i || {}; ttq._i[e] = []; ttq._i[e]._u = i; ttq._t = ttq._t || {}; ttq._t[e] = +new Date(); ttq._o = ttq._o || {}; ttq._o[e] = n || {};
        var o = d.createElement("script"); o.type = "text/javascript"; o.async = !0; o.src = i + "?sdkid=" + e + "&lib=" + t;
        var a = d.getElementsByTagName("script")[0]; a.parentNode.insertBefore(o, a);
      };
    })(window, document, "ttq");
  }
  window.ttq.load(id);
  loaded.tiktok = true;
}
/* eslint-enable */

function maybeLoad() {
  if (!marketingAllowed()) return;
  let justLoaded = false;
  if (ids.meta && !loaded.meta) { loadMeta(ids.meta); justLoaded = true; }
  if (ids.tiktok && !loaded.tiktok) { loadTikTok(ids.tiktok); justLoaded = true; }
  if (justLoaded) trackPageView();
}

export async function initPixels() {
  if (!fetched) {
    fetched = true;
    try {
      const { data } = await api.get("/settings/pixels");
      ids.meta = data?.meta_pixel_id || null;
      ids.tiktok = data?.tiktok_pixel_id || null;
    } catch { /* pixels are best-effort */ }
  }
  if (!listenerAttached) {
    listenerAttached = true;
    window.addEventListener("smp:cookie-consent", maybeLoad);
  }
  maybeLoad();
}

const money = (value, currency) =>
  Number.isFinite(Number(value)) && Number(value) > 0
    ? { value: Number(value), currency: currency || "USD" }
    : undefined;

export function trackPageView() {
  try {
    if (loaded.meta && window.fbq) window.fbq("track", "PageView");
    if (loaded.tiktok && window.ttq) window.ttq.page();
  } catch { /* noop */ }
}

export function trackSignUp() {
  try {
    if (loaded.meta && window.fbq) window.fbq("track", "CompleteRegistration");
    if (loaded.tiktok && window.ttq) window.ttq.track("CompleteRegistration", {});
  } catch { /* noop */ }
}

export function trackInitiateCheckout(value, currency) {
  const m = money(value, currency);
  try {
    if (loaded.meta && window.fbq) window.fbq("track", "InitiateCheckout", m);
    if (loaded.tiktok && window.ttq) window.ttq.track("InitiateCheckout", m || {});
  } catch { /* noop */ }
}

export function trackPurchase(value, currency) {
  const m = money(value, currency);
  try {
    if (loaded.meta && window.fbq) window.fbq("track", "Purchase", m || { value: 0, currency: "USD" });
    if (loaded.tiktok && window.ttq) window.ttq.track("CompletePayment", m || {});
  } catch { /* noop */ }
}
