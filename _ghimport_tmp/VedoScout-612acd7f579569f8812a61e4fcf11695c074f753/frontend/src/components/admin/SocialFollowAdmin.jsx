// SocialFollowAdmin — manage the landing "follow us" boxes (links + follower counts).
import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Instagram, Facebook } from "lucide-react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

export default function SocialFollowAdmin() {
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/admin/social-follow").then(({ data }) => setForm(data)).catch(() => toast.error("Could not load social settings"));
  }, []);

  const set = (net, field, value) => setForm((f) => ({ ...f, [net]: { ...f[net], [field]: value } }));

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/admin/social-follow", {
        enabled: form.enabled !== false,
        instagram: { url: (form.instagram?.url || "").trim(), followers: Math.max(0, parseInt(form.instagram?.followers, 10) || 0) },
        facebook: { url: (form.facebook?.url || "").trim(), followers: Math.max(0, parseInt(form.facebook?.followers, 10) || 0) },
      });
      toast.success("Social follow boxes updated");
    } catch {
      toast.error("Could not save");
    } finally {
      setSaving(false);
    }
  };

  if (!form) return <div className="text-ink/50 text-sm py-6">Loading social settings…</div>;

  const nets = [
    { key: "instagram", label: "Instagram", icon: Instagram, placeholder: "https://www.instagram.com/scoutmeplay" },
    { key: "facebook", label: "Facebook", icon: Facebook, placeholder: "https://www.facebook.com/scoutmeplay" },
  ];

  return (
    <div className="space-y-4" data-testid="social-follow-admin">
      <div className="flex items-center justify-between rounded-lg border border-ink/10 bg-white/5 px-4 py-3">
        <div>
          <div className="font-bold text-ink">Follow-us section (landing)</div>
          <div className="text-xs text-ink/50">Two boxes with your Instagram &amp; Facebook links and follower counts.</div>
        </div>
        <Switch checked={form.enabled !== false} onCheckedChange={(v) => setForm((f) => ({ ...f, enabled: v }))} data-testid="social-follow-enabled" />
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        {nets.map(({ key, label, icon: Icon, placeholder }) => (
          <div key={key} className="rounded-lg border border-ink/10 p-4 space-y-3">
            <div className="flex items-center gap-2 font-bold text-ink text-sm"><Icon className="w-4 h-4" /> {label}</div>
            <div>
              <label className="text-[11px] uppercase tracking-wider text-ink/40 font-bold">Page link</label>
              <Input value={form[key]?.url || ""} placeholder={placeholder} onChange={(e) => set(key, "url", e.target.value)} data-testid={`social-url-${key}`} />
            </div>
            <div>
              <label className="text-[11px] uppercase tracking-wider text-ink/40 font-bold">Followers shown</label>
              <Input type="number" min="0" value={form[key]?.followers ?? 0} onChange={(e) => set(key, "followers", e.target.value)} data-testid={`social-followers-${key}`} />
            </div>
          </div>
        ))}
      </div>
      <Button onClick={save} disabled={saving} data-testid="social-follow-save">{saving ? "Saving…" : "Save social boxes"}</Button>
    </div>
  );
}
