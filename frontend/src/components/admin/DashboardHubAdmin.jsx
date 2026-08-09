// DashboardHubAdmin — controls for the player dashboard:
// 1) ScoutMePlay Network numbers  2) Messages & notifications composer
// 3) Trials & Opportunities (premium-only section on the dashboard)
import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { TrendingUp, Send, Trophy, Trash2, Loader2, Eye, EyeOff } from "lucide-react";

const inp = "bg-white border border-gray-border rounded-lg px-3 py-2 text-sm text-ink focus:outline-none focus:border-forest w-full";
const lbl = "block text-[10px] font-extrabold uppercase tracking-wider text-ink/55 mb-1";
const btn = "inline-flex items-center gap-2 bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-xs px-4 py-2.5 rounded-lg transition-colors disabled:opacity-50";

const NUM_FIELDS = [
  ["players_in_library", "Players in library", "players_wk", "+/week"],
  ["clubs_looking", "Clubs looking", "clubs_wk", "+/week"],
  ["scouts_searching", "Scouts searching", "scouts_wk", "+/week"],
  ["active_agents", "Active agents", "agents_wk", "+/week"],
  ["trial_invites", "Trial invites", "trials_wk", "+/week"],
];

export default function DashboardHubAdmin() {
  return (
    <div data-testid="dashboard-hub-admin">
      <CommunityNumbersCard />
      <MessageComposerCard />
      <OpportunitiesCard />
    </div>
  );
}

function CommunityNumbersCard() {
  const [cfg, setCfg] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/admin/dashboard/community")
      .then(({ data }) => setCfg(data))
      .catch(() => toast.error("Could not load network numbers"));
  }, []);

  const save = async () => {
    setBusy(true);
    try {
      const payload = { enabled: !!cfg.enabled };
      NUM_FIELDS.forEach(([k, , wk]) => {
        payload[k] = Number(cfg[k]) || 0;
        payload[wk] = Number(cfg[wk]) || 0;
      });
      const { data } = await api.put("/admin/dashboard/community", payload);
      setCfg(data);
      toast.success("Network numbers saved");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    } finally {
      setBusy(false);
    }
  };

  if (!cfg) return null;
  return (
    <section className="bg-white border border-gray-border rounded-2xl p-5" data-testid="community-numbers-admin">
      <h3 className="font-barlow font-black uppercase text-ink flex items-center gap-2">
        <TrendingUp className="w-4 h-4 text-forest" /> ScoutMePlay Network numbers
      </h3>
      <p className="text-xs text-ink/55 mt-1">
        Shown on every player dashboard ("ScoutMePlay Network" section). Set to 0 to hide a stat, or disable the whole section.
      </p>
      <label className="flex items-center gap-2 mt-4 text-sm text-ink/80 font-semibold">
        <input
          type="checkbox"
          checked={!!cfg.enabled}
          data-testid="community-enabled-toggle"
          onChange={(e) => setCfg({ ...cfg, enabled: e.target.checked })}
        />
        Show the Network section on dashboards
      </label>
      <div className="mt-4 grid grid-cols-2 md:grid-cols-5 gap-3">
        {NUM_FIELDS.map(([k, label, wk, wkLabel]) => (
          <div key={k}>
            <label className={lbl}>{label}</label>
            <input
              type="number"
              className={inp}
              value={cfg[k] ?? 0}
              data-testid={`community-input-${k}`}
              onChange={(e) => setCfg({ ...cfg, [k]: e.target.value })}
            />
            <label className={`${lbl} mt-2`}>{wkLabel}</label>
            <input
              type="number"
              className={inp}
              value={cfg[wk] ?? 0}
              data-testid={`community-input-${wk}`}
              onChange={(e) => setCfg({ ...cfg, [wk]: e.target.value })}
            />
          </div>
        ))}
      </div>
      <button type="button" onClick={save} disabled={busy} className={`${btn} mt-4`} data-testid="community-save-btn">
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : "Save numbers"}
      </button>
    </section>
  );
}

const EMPTY_MSG = {
  kind: "notification",
  sender_type: "admin",
  sender_name: "ScoutMePlay Team",
  subject: "",
  body: "",
  target: "all",
  target_email: "",
  link: "",
};

function MessageComposerCard() {
  const [form, setForm] = useState(EMPTY_MSG);
  const [sent, setSent] = useState([]);
  const [busy, setBusy] = useState(false);

  const load = () => {
    api.get("/admin/dashboard/messages").then(({ data }) => setSent(data.messages || [])).catch(() => {});
  };
  useEffect(load, []);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const send = async () => {
    if (!form.subject.trim() || !form.body.trim()) {
      toast.error("Subject and body are required");
      return;
    }
    setBusy(true);
    try {
      await api.post("/admin/dashboard/messages", {
        ...form,
        target_email: form.target_email.trim() || null,
        link: form.link.trim() || null,
      });
      toast.success(form.target_email.trim() ? `Sent to ${form.target_email.trim()}` : `Sent to ${form.target} users`);
      setForm({ ...EMPTY_MSG, kind: form.kind, sender_type: form.sender_type, sender_name: form.sender_name });
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Send failed");
    } finally {
      setBusy(false);
    }
  };

  const del = async (id) => {
    try {
      await api.delete(`/admin/dashboard/messages/${id}`);
      setSent((prev) => prev.filter((m) => m.id !== id));
      toast.success("Deleted");
    } catch {
      toast.error("Delete failed");
    }
  };

  return (
    <section className="bg-white border border-gray-border rounded-2xl p-5 mt-6" data-testid="message-composer-admin">
      <h3 className="font-barlow font-black uppercase text-ink flex items-center gap-2">
        <Send className="w-4 h-4 text-forest" /> Dashboard messages &amp; notifications
      </h3>
      <p className="text-xs text-ink/55 mt-1">
        Send in-app notifications or messages to all users, a membership segment, or one specific user.
        Scout/agent/club-style messages are ONLY visible to Premium/VIP members — free users see a locked teaser.
      </p>
      <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3">
        <div>
          <label className={lbl}>Type</label>
          <select className={inp} value={form.kind} onChange={set("kind")} data-testid="composer-kind">
            <option value="notification">Notification</option>
            <option value="message">Message (inbox)</option>
          </select>
        </div>
        <div>
          <label className={lbl}>Sender type</label>
          <select className={inp} value={form.sender_type} onChange={set("sender_type")} data-testid="composer-sender-type">
            <option value="admin">ScoutMePlay (admin)</option>
            <option value="scout">Scout</option>
            <option value="agent">Agent</option>
            <option value="club">Club</option>
          </select>
        </div>
        <div>
          <label className={lbl}>Sender display name</label>
          <input className={inp} value={form.sender_name} onChange={set("sender_name")} data-testid="composer-sender-name" placeholder="e.g. Scout Fatima A." />
        </div>
        <div>
          <label className={lbl}>Target</label>
          <select className={inp} value={form.target} onChange={set("target")} data-testid="composer-target">
            <option value="all">All users</option>
            <option value="free">Free members</option>
            <option value="premium">Premium members</option>
            <option value="vip">VIP members</option>
          </select>
        </div>
      </div>
      <div className="mt-3 grid md:grid-cols-2 gap-3">
        <div>
          <label className={lbl}>Or one specific user (email — overrides target)</label>
          <input className={inp} value={form.target_email} onChange={set("target_email")} data-testid="composer-target-email" placeholder="player@email.com" />
        </div>
        <div>
          <label className={lbl}>Optional link</label>
          <input className={inp} value={form.link} onChange={set("link")} data-testid="composer-link" placeholder="https://…" />
        </div>
      </div>
      <div className="mt-3">
        <label className={lbl}>Subject</label>
        <input className={inp} value={form.subject} onChange={set("subject")} data-testid="composer-subject" placeholder="Your report is ready!" />
      </div>
      <div className="mt-3">
        <label className={lbl}>Body</label>
        <textarea className={`${inp} min-h-[90px]`} value={form.body} onChange={set("body")} data-testid="composer-body" placeholder="Write the message players will see on their dashboard…" />
      </div>
      <button type="button" onClick={send} disabled={busy} className={`${btn} mt-4`} data-testid="composer-send-btn">
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <><Send className="w-3.5 h-3.5" /> Send</>}
      </button>

      {sent.length > 0 && (
        <div className="mt-6">
          <h4 className="text-[11px] font-extrabold uppercase tracking-wider text-ink/55">Sent ({sent.length})</h4>
          <ul className="mt-2 divide-y divide-gray-border border border-gray-border rounded-xl overflow-hidden">
            {sent.slice(0, 20).map((m) => (
              <li key={m.id} className="flex items-center gap-3 px-3.5 py-2.5 bg-white" data-testid={`sent-message-${m.id}`}>
                <span className={`text-[9px] uppercase tracking-wider font-black px-2 py-0.5 rounded-full shrink-0 ${m.kind === "message" ? "bg-blue-100 text-blue-700" : "bg-forest/10 text-forest"}`}>
                  {m.kind}
                </span>
                <div className="min-w-0 flex-1">
                  <b className="block text-[13px] text-ink truncate">{m.subject}</b>
                  <span className="block text-[11px] text-ink/50 truncate">
                    {m.sender_name} ({m.sender_type}) → {m.target_email || m.target} · {m.read_count || 0} read
                  </span>
                </div>
                <button type="button" onClick={() => del(m.id)} data-testid={`delete-message-${m.id}`} className="text-ink/40 hover:text-red-600 p-1.5 shrink-0" aria-label="Delete message">
                  <Trash2 className="w-4 h-4" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

const EMPTY_OPP = { title: "", club_name: "", age_band: "", location: "", deadline: "", cta_url: "" };

function OpportunitiesCard() {
  const [form, setForm] = useState(EMPTY_OPP);
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);

  const load = () => {
    api.get("/admin/dashboard/opportunities").then(({ data }) => setItems(data.items || [])).catch(() => {});
  };
  useEffect(load, []);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const create = async () => {
    if (!form.title.trim()) {
      toast.error("Title is required");
      return;
    }
    setBusy(true);
    try {
      await api.post("/admin/dashboard/opportunities", {
        ...form,
        deadline: form.deadline || null,
        cta_url: form.cta_url.trim() || null,
      });
      toast.success("Opportunity created");
      setForm(EMPTY_OPP);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Create failed");
    } finally {
      setBusy(false);
    }
  };

  const toggleActive = async (o) => {
    try {
      await api.put(`/admin/dashboard/opportunities/${o.id}`, { active: !o.active });
      setItems((prev) => prev.map((x) => (x.id === o.id ? { ...x, active: !o.active } : x)));
    } catch {
      toast.error("Update failed");
    }
  };

  const del = async (id) => {
    try {
      await api.delete(`/admin/dashboard/opportunities/${id}`);
      setItems((prev) => prev.filter((x) => x.id !== id));
      toast.success("Deleted");
    } catch {
      toast.error("Delete failed");
    }
  };

  return (
    <section className="bg-white border border-gray-border rounded-2xl p-5 mt-6" data-testid="opportunities-admin">
      <h3 className="font-barlow font-black uppercase text-ink flex items-center gap-2">
        <Trophy className="w-4 h-4 text-forest" /> Trials &amp; Opportunities
      </h3>
      <p className="text-xs text-ink/55 mt-1">
        Shown ONLY to Premium/VIP members on their dashboard. Free users never see this section.
      </p>
      <div className="mt-4 grid grid-cols-2 md:grid-cols-3 gap-3">
        <div className="col-span-2 md:col-span-1">
          <label className={lbl}>Title *</label>
          <input className={inp} value={form.title} onChange={set("title")} data-testid="opp-input-title" placeholder="Elite Football Academy Trials" />
        </div>
        <div>
          <label className={lbl}>Club</label>
          <input className={inp} value={form.club_name} onChange={set("club_name")} data-testid="opp-input-club" placeholder="Elite FC" />
        </div>
        <div>
          <label className={lbl}>Age band</label>
          <input className={inp} value={form.age_band} onChange={set("age_band")} data-testid="opp-input-age" placeholder="U16" />
        </div>
        <div>
          <label className={lbl}>Location</label>
          <input className={inp} value={form.location} onChange={set("location")} data-testid="opp-input-location" placeholder="London, UK" />
        </div>
        <div>
          <label className={lbl}>Deadline</label>
          <input type="date" className={inp} value={form.deadline} onChange={set("deadline")} data-testid="opp-input-deadline" />
        </div>
        <div>
          <label className={lbl}>Link (optional)</label>
          <input className={inp} value={form.cta_url} onChange={set("cta_url")} data-testid="opp-input-cta" placeholder="https://…" />
        </div>
      </div>
      <button type="button" onClick={create} disabled={busy} className={`${btn} mt-4`} data-testid="opp-create-btn">
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : "Add opportunity"}
      </button>

      {items.length > 0 && (
        <ul className="mt-5 divide-y divide-gray-border border border-gray-border rounded-xl overflow-hidden">
          {items.map((o) => (
            <li key={o.id} className={`flex items-center gap-3 px-3.5 py-2.5 ${o.active ? "bg-white" : "bg-gray-50 opacity-60"}`} data-testid={`opp-row-${o.id}`}>
              <div className="min-w-0 flex-1">
                <b className="block text-[13px] text-ink truncate">{o.title}</b>
                <span className="block text-[11px] text-ink/50 truncate">
                  {[o.club_name, o.age_band, o.location].filter(Boolean).join(" • ")}
                  {o.deadline ? ` · deadline ${o.deadline}` : ""}
                </span>
              </div>
              <button type="button" onClick={() => toggleActive(o)} data-testid={`opp-toggle-${o.id}`} className="text-ink/50 hover:text-forest p-1.5 shrink-0" aria-label={o.active ? "Deactivate" : "Activate"} title={o.active ? "Visible — click to hide" : "Hidden — click to show"}>
                {o.active ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
              </button>
              <button type="button" onClick={() => del(o.id)} data-testid={`opp-delete-${o.id}`} className="text-ink/40 hover:text-red-600 p-1.5 shrink-0" aria-label="Delete opportunity">
                <Trash2 className="w-4 h-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
