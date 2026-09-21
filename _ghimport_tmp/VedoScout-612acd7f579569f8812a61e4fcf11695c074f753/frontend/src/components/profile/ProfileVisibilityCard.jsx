import React, { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import {
  Camera, Upload, Eye, EyeOff, Loader2, Shield, Trash2, Sparkles,
  UserCircle2, CheckCircle2, Info, X, Lock,
} from "lucide-react";
import api from "@/lib/api";

const POSITIONS = ["GK", "CB", "FB", "DM", "CM", "CAM", "W", "ST"];
const FEET = ["left", "right", "both"];

const abs = (path) =>
  path && path.startsWith("http") ? path : `${process.env.REACT_APP_BACKEND_URL}${path}`;

const currentYear = new Date().getFullYear();
const isMinor = (birthYear) => {
  if (!birthYear) return false;
  return currentYear - Number(birthYear) < 16;
};

export default function ProfileVisibilityCard({ latestReportId, premiumAccess = true }) {
  const [profile, setProfile] = useState(null);
  const [saving, setSaving] = useState(false);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const [autoGenerating, setAutoGenerating] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => {
    api.get("/profile/me")
      .then(({ data }) => setProfile(data))
      .catch(() => { /* silent */ });
  }, []);

  const minor = useMemo(() => isMinor(profile?.birth_year), [profile?.birth_year]);

  if (!profile) {
    return (
      <section
        data-testid="profile-visibility-card"
        className="mt-10 border border-ink/10 bg-cream-card p-6 md:p-8 animate-pulse"
      >
        <div className="h-4 w-32 bg-ink/10 mb-3" />
        <div className="h-6 w-64 bg-ink/10" />
      </section>
    );
  }

  const patch = async (updates) => {
    setSaving(true);
    try {
      const { data } = await api.put("/profile/me", updates);
      setProfile(data);
      return data;
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not save profile", { duration: 5000 });
      throw err;
    } finally {
      setSaving(false);
    }
  };

  const toggleDiscoverable = async (next) => {
    if (next && !premiumAccess) {
      toast.info("Scout Library visibility is a Premium feature. Upgrade to be visible to scouts.", { duration: 6000 });
      return;
    }
    if (next && minor && !profile.parent_consent) {
      toast.info("Parental consent required for players under 16.", { duration: 6000 });
      setExpanded(true);
      return;
    }
    try {
      await patch({ discoverable: next });
      toast.success(next ? "You're now visible to scouts." : "You're no longer visible to scouts.");
    } catch { /* toasted */ }
  };

  const handleAvatarFile = async (file) => {
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      toast.error("Avatar must be 5 MB or smaller.");
      return;
    }
    setUploadingAvatar(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const { data } = await api.post("/profile/avatar/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setProfile((p) => ({ ...p, avatar_url: data.avatar_url, avatar_source: data.avatar_source }));
      toast.success("Avatar updated.");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Upload failed", { duration: 5000 });
    } finally {
      setUploadingAvatar(false);
    }
  };

  const handleAutoAvatar = async () => {
    if (!latestReportId) {
      toast.info("Upload a video first — the avatar comes from your marked player.");
      return;
    }
    setAutoGenerating(true);
    try {
      const { data } = await api.post(`/profile/avatar/from-report/${latestReportId}`);
      setProfile((p) => ({ ...p, avatar_url: data.avatar_url, avatar_source: data.avatar_source }));
      toast.success("Avatar generated from your video.");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not generate avatar", { duration: 6000 });
    } finally {
      setAutoGenerating(false);
    }
  };

  const removeAvatar = async () => {
    if (!profile.avatar_url) return;
    try {
      await api.delete("/profile/avatar");
      setProfile((p) => ({ ...p, avatar_url: null, avatar_source: null }));
      toast.success("Avatar removed.");
    } catch {
      toast.error("Could not remove avatar.");
    }
  };

  const updatePublicField = async (field, value) => {
    try {
      await patch({ public_profile: { [field]: value || null } });
    } catch { /* toasted */ }
  };

  const initial = (profile.full_name || "?").trim().charAt(0).toUpperCase();
  const isDiscoverable = profile.discoverable;

  return (
    <section
      data-testid="profile-visibility-card"
      className="mt-10 border border-ink/10 bg-cream-card overflow-hidden"
    >
      {/* Header row */}
      <div className="flex items-center justify-between gap-4 px-6 md:px-8 py-5 border-b border-ink/10 bg-cream-base/40">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 border-2 border-forest flex items-center justify-center">
            <UserCircle2 className="w-5 h-5 text-forest" strokeWidth={2} />
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.24em] font-black text-forest">
              Scout profile
            </div>
            <h3 className="font-barlow font-black uppercase text-xl md:text-2xl tracking-tight leading-none mt-0.5">
              Your visibility
            </h3>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          data-testid="profile-toggle-expand"
          className="text-[11px] uppercase tracking-[0.18em] font-black text-forest hover:text-forest-pop transition-colors"
        >
          {expanded ? "Collapse" : "Edit profile"}
        </button>
      </div>

      {/* Main row: avatar + discoverable toggle */}
      <div className="grid md:grid-cols-[auto,1fr] gap-6 md:gap-8 px-6 md:px-8 py-6">
        {/* AVATAR block */}
        <div className="flex flex-col items-start gap-3">
          <div className="relative w-28 h-28 border-2 border-forest bg-forest/10 flex items-center justify-center overflow-hidden">
            {profile.avatar_url ? (
              <img
                src={abs(profile.avatar_url)}
                alt="Your avatar"
                className="w-full h-full object-cover"
                data-testid="profile-avatar-img"
              />
            ) : (
              <span className="font-barlow font-black text-4xl text-forest select-none">
                {initial}
              </span>
            )}
            {(uploadingAvatar || autoGenerating) && (
              <div className="absolute inset-0 bg-ink/70 flex items-center justify-center">
                <Loader2 className="w-6 h-6 text-white animate-spin" />
              </div>
            )}
          </div>
          <div className="flex flex-col gap-1.5 w-full">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploadingAvatar}
              data-testid="profile-avatar-upload-btn"
              className="inline-flex items-center gap-2 text-[11px] uppercase tracking-widest font-black text-forest hover:text-forest-pop transition-colors disabled:opacity-50"
            >
              <Upload className="w-3.5 h-3.5" /> Upload photo
            </button>
            <button
              type="button"
              onClick={handleAutoAvatar}
              disabled={autoGenerating || !latestReportId}
              data-testid="profile-avatar-auto-btn"
              title={!latestReportId ? "Upload a video first" : "Generate from your marked player in your latest video"}
              className="inline-flex items-center gap-2 text-[11px] uppercase tracking-widest font-black text-forest hover:text-forest-pop transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Sparkles className="w-3.5 h-3.5" /> Auto from video
            </button>
            {profile.avatar_url && (
              <button
                type="button"
                onClick={removeAvatar}
                data-testid="profile-avatar-remove-btn"
                className="inline-flex items-center gap-2 text-[11px] uppercase tracking-widest font-black text-ink/50 hover:text-red-600 transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5" /> Remove
              </button>
            )}
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            data-testid="profile-avatar-file-input"
            className="hidden"
            onChange={(e) => handleAvatarFile(e.target.files?.[0])}
          />
        </div>

        {/* DISCOVERABLE toggle + copy */}
        <div className="flex flex-col justify-center">
          <div className="flex items-start justify-between gap-4 mb-3">
            <div>
              <div className="flex items-center gap-2">
                {isDiscoverable
                  ? <Eye className="w-4 h-4 text-forest-pop" />
                  : <EyeOff className="w-4 h-4 text-ink/40" />}
                <h4 className="font-barlow font-black uppercase text-lg tracking-tight">
                  {isDiscoverable ? "Visible to scouts" : "Hidden from scouts"}
                </h4>
              </div>
              <p className="mt-1.5 text-sm text-ink/70 leading-relaxed max-w-md">
                {isDiscoverable ? (
                  <>You appear in the paid scout database. Scouts, agents and clubs with an active
                  subscription can search, view your stats and request contact.</>
                ) : !premiumAccess ? (
                  <>Scout Library visibility is a <strong>Premium privilege</strong> — scouts, agents
                  and clubs can only discover Premium players.</>
                ) : (
                  <>Turn this on to let professional scouts, agents and clubs discover you. Your
                  private data (email, phone) is never shown — only your stats and video preview.</>
                )}
              </p>
            </div>

            {/* iOS-style toggle */}
            <button
              type="button"
              role="switch"
              aria-checked={isDiscoverable}
              onClick={() => toggleDiscoverable(!isDiscoverable)}
              disabled={saving}
              data-testid="profile-discoverable-toggle"
              className={`shrink-0 relative w-14 h-8 border-2 transition-colors ${
                isDiscoverable
                  ? "bg-forest border-forest"
                  : !premiumAccess
                  ? "bg-cream-base border-ink/15 opacity-60 cursor-not-allowed"
                  : "bg-cream-base border-ink/20"
              }`}
            >
              {!premiumAccess && !isDiscoverable ? (
                <Lock className="absolute inset-0 m-auto w-3.5 h-3.5 text-ink/40" />
              ) : (
                <span
                  className={`absolute top-0.5 left-0.5 w-6 h-6 bg-white transition-transform ${
                    isDiscoverable ? "translate-x-6" : "translate-x-0"
                  }`}
                />
              )}
            </button>
          </div>

          {/* Free-plan lock notice */}
          {!premiumAccess && (
            <div
              className="mt-2 border border-amber-400 bg-amber-50 p-3 flex gap-2.5"
              data-testid="visibility-locked-notice"
            >
              <Lock className="w-4 h-4 shrink-0 mt-0.5 text-amber-700" />
              <div className="flex-1 text-[13px] leading-snug">
                <strong className="text-amber-800">On the Free plan your uploads can't be seen by scouts.</strong>{" "}
                Upgrade to Premium to enter the Scout Library. Want exposure anyway? Opt in to
                social-media featuring further down the page — that's the one place we can show your clip.
              </div>
            </div>
          )}

          {/* Minor consent notice */}
          {minor && (
            <div
              className={`mt-2 border p-3 flex gap-2.5 ${
                profile.parent_consent
                  ? "border-forest/30 bg-forest/5"
                  : "border-amber-400 bg-amber-50"
              }`}
            >
              <Shield className={`w-4 h-4 shrink-0 mt-0.5 ${
                profile.parent_consent ? "text-forest" : "text-amber-700"
              }`} />
              <div className="flex-1 text-[13px] leading-snug">
                {profile.parent_consent ? (
                  <><strong className="text-forest">Parental consent on file.</strong> A parent/guardian
                    has approved this player being visible in the scout database.</>
                ) : (
                  <><strong className="text-amber-800">Parental consent required.</strong> Players under 16
                    must have a parent/guardian confirm before being visible to scouts.</>
                )}
                {!profile.parent_consent && (
                  <label
                    className="flex items-center gap-2 mt-2 text-[12px] font-bold text-amber-900 cursor-pointer"
                    data-testid="profile-parent-consent-row"
                  >
                    <input
                      type="checkbox"
                      className="w-4 h-4 accent-forest"
                      data-testid="profile-parent-consent-checkbox"
                      onChange={(e) => patch({ parent_consent: e.target.checked })}
                    />
                    I am the parent/guardian and I consent.
                  </label>
                )}
              </div>
            </div>
          )}

          {/* Quick discoverable status pill */}
          {isDiscoverable && (
            <div
              className="mt-3 inline-flex items-center gap-2 text-[11px] uppercase tracking-[0.16em] font-black text-forest-pop"
              data-testid="profile-discoverable-status"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              Live in scout database
            </div>
          )}
        </div>
      </div>

      {/* Expanded: public profile fields */}
      {expanded && (
        <div
          data-testid="profile-expanded-fields"
          className="border-t border-ink/10 bg-cream-base/40 px-6 md:px-8 py-6"
        >
          <div className="flex items-center gap-2 mb-4">
            <Info className="w-4 h-4 text-forest" />
            <p className="text-[12px] uppercase tracking-[0.16em] font-black text-forest">
              Public profile — shown to scouts who match your position/age
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-4">
            <Field label="Birth year">
              <input
                type="number"
                min="1990"
                max={currentYear}
                data-testid="profile-birth-year"
                defaultValue={profile.birth_year || ""}
                onBlur={(e) => {
                  const v = e.target.value ? Number(e.target.value) : null;
                  if (v !== (profile.birth_year || null)) patch({ birth_year: v });
                }}
                className="w-full border border-ink/15 bg-white px-3 py-2 text-sm focus:border-forest focus:outline-none"
                placeholder="2012"
              />
            </Field>

            <Field label="Primary position">
              <select
                defaultValue={profile.public_profile.position || ""}
                data-testid="profile-position"
                onChange={(e) => updatePublicField("position", e.target.value)}
                className="w-full border border-ink/15 bg-white px-3 py-2 text-sm focus:border-forest focus:outline-none"
              >
                <option value="">—</option>
                {POSITIONS.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </Field>

            <Field label="Preferred foot">
              <select
                defaultValue={profile.public_profile.preferred_foot || ""}
                data-testid="profile-foot"
                onChange={(e) => updatePublicField("preferred_foot", e.target.value)}
                className="w-full border border-ink/15 bg-white px-3 py-2 text-sm focus:border-forest focus:outline-none"
              >
                <option value="">—</option>
                {FEET.map((f) => <option key={f} value={f}>{f.charAt(0).toUpperCase() + f.slice(1)}</option>)}
              </select>
            </Field>

            <Field label="Height (cm)">
              <input
                type="number" min="80" max="230"
                data-testid="profile-height"
                defaultValue={profile.public_profile.height_cm || ""}
                onBlur={(e) => updatePublicField("height_cm", e.target.value ? Number(e.target.value) : null)}
                className="w-full border border-ink/15 bg-white px-3 py-2 text-sm focus:border-forest focus:outline-none"
                placeholder="168"
              />
            </Field>

            <Field label="Weight (kg)">
              <input
                type="number" min="20" max="150"
                data-testid="profile-weight"
                defaultValue={profile.public_profile.weight_kg || ""}
                onBlur={(e) => updatePublicField("weight_kg", e.target.value ? Number(e.target.value) : null)}
                className="w-full border border-ink/15 bg-white px-3 py-2 text-sm focus:border-forest focus:outline-none"
                placeholder="58"
              />
            </Field>

            <Field label="Country">
              <input
                type="text" maxLength={40}
                data-testid="profile-country"
                defaultValue={profile.public_profile.country || ""}
                onBlur={(e) => updatePublicField("country", e.target.value.trim())}
                className="w-full border border-ink/15 bg-white px-3 py-2 text-sm focus:border-forest focus:outline-none"
                placeholder="Denmark"
              />
            </Field>

            <Field label="Current club">
              <input
                type="text" maxLength={60}
                data-testid="profile-club"
                defaultValue={profile.public_profile.club || ""}
                onBlur={(e) => updatePublicField("club", e.target.value.trim())}
                className="w-full border border-ink/15 bg-white px-3 py-2 text-sm focus:border-forest focus:outline-none"
                placeholder="AB U14"
              />
            </Field>

            <div className="md:col-span-2">
              <Field label="Short bio (optional)">
                <textarea
                  rows={2} maxLength={240}
                  data-testid="profile-bio"
                  defaultValue={profile.public_profile.bio || ""}
                  onBlur={(e) => updatePublicField("bio", e.target.value.trim())}
                  className="w-full border border-ink/15 bg-white px-3 py-2 text-sm focus:border-forest focus:outline-none resize-none"
                  placeholder="Two sentences scouts see first. What sets you apart?"
                />
              </Field>
            </div>
          </div>

          <button
            type="button"
            onClick={() => setExpanded(false)}
            className="mt-6 inline-flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] font-black text-ink/60 hover:text-ink transition-colors"
          >
            <X className="w-3.5 h-3.5" /> Close
          </button>
        </div>
      )}
    </section>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <div className="text-[10px] uppercase tracking-[0.18em] font-black text-forest mb-1.5">
        {label}
      </div>
      {children}
    </label>
  );
}
