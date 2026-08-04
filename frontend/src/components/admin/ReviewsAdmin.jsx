// ReviewsAdmin — moderate user reviews + add manual ones (text, stars, image).
import React, { useEffect, useState } from "react";
import { Star, Trash2, Plus } from "lucide-react";
import api from "@/lib/api";
import { toast } from "sonner";

const ASSET_BASE = process.env.REACT_APP_BACKEND_URL || "";

export default function ReviewsAdmin() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ name: "", stars: 5, text: "" });
  const [imageB64, setImageB64] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () => api.get("/admin/reviews").then(({ data }) => setItems(data.items || [])).catch(() => {});
  useEffect(() => { load(); }, []);

  const onFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => setImageB64(reader.result);
    reader.readAsDataURL(f);
  };

  const add = async () => {
    if (!form.name.trim() || !form.text.trim()) { toast.error("Name and text required"); return; }
    setBusy(true);
    try {
      await api.post("/admin/reviews", { ...form, image_base64: imageB64 });
      toast.success("Review added");
      setForm({ name: "", stars: 5, text: "" });
      setImageB64(null);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
    finally { setBusy(false); }
  };

  const del = async (id) => {
    try { await api.delete(`/admin/reviews/${id}`); toast.success("Deleted"); load(); }
    catch { toast.error("Failed"); }
  };

  const inp = "bg-white border border-gray-border rounded-lg px-3 py-2 text-sm text-ink focus:outline-none focus:border-forest";

  return (
    <div className="space-y-8" data-testid="reviews-admin">
      <section className="bg-white border border-gray-border rounded-2xl p-5">
        <h3 className="font-barlow font-black uppercase text-ink flex items-center gap-2"><Plus className="w-4 h-4 text-forest" /> Add review manually</h3>
        <div className="grid sm:grid-cols-3 gap-3 mt-3">
          <input placeholder="Name (e.g. Noah's dad)" value={form.name} data-testid="admin-review-name"
            onChange={(e) => setForm({ ...form, name: e.target.value })} className={inp} />
          <div className="flex items-center gap-1">
            {[1, 2, 3, 4, 5].map((i) => (
              <button key={i} type="button" onClick={() => setForm({ ...form, stars: i })} data-testid={`admin-review-star-${i}`}>
                <Star className="w-6 h-6" style={{ color: i <= form.stars ? "#B9CE00" : "#D8D3C4", fill: i <= form.stars ? "#B9CE00" : "none" }} />
              </button>
            ))}
          </div>
          <input type="file" accept="image/*" onChange={onFile} data-testid="admin-review-image" className="text-xs" />
        </div>
        <textarea rows={2} maxLength={180} placeholder="Two lines of review text…" value={form.text} data-testid="admin-review-text"
          onChange={(e) => setForm({ ...form, text: e.target.value })} className={`${inp} w-full mt-3 resize-none`} />
        <button type="button" onClick={add} disabled={busy} data-testid="admin-review-add-btn"
          className="mt-3 bg-forest text-white font-barlow font-black uppercase text-[11px] tracking-widest px-6 py-2.5 rounded-full disabled:opacity-50">
          Publish review
        </button>
      </section>

      <section className="space-y-2">
        {items.map((r) => (
          <div key={r.id} className="flex items-center gap-4 bg-white border border-gray-border rounded-xl px-4 py-3" data-testid={`admin-review-row-${r.id}`}>
            {r.image_url ? (
              <img src={r.image_url.startsWith("http") ? r.image_url : `${ASSET_BASE}${r.image_url}`} alt="" className="w-10 h-10 rounded-full object-cover" />
            ) : (
              <span className="w-10 h-10 rounded-full bg-[#12402A] text-[#CCFF00] flex items-center justify-center font-black">{(r.name || "?")[0]}</span>
            )}
            <div className="flex-1 min-w-0">
              <div className="text-sm font-bold text-ink">{r.name} <span className="text-[10px] uppercase text-ink/40 ml-1">{r.source}</span></div>
              <div className="text-xs text-ink/60 truncate">{"★".repeat(r.stars)} — {r.text}</div>
            </div>
            <button type="button" onClick={() => del(r.id)} data-testid={`admin-review-delete-${r.id}`} className="text-red-600 hover:text-red-800">
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        ))}
        {!items.length && <p className="text-xs text-ink/40">No reviews yet.</p>}
      </section>
    </div>
  );
}
