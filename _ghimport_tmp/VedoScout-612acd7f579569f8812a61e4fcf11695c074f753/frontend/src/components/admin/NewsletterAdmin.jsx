// NewsletterAdmin — subscriber list for the weekly letter.
import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Mail, Trash2, X } from "lucide-react";
import api from "@/lib/api";

export default function NewsletterAdmin({ onClose }) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/admin/newsletter");
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (e) {
      toast.error("Failed to load subscribers");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const remove = async (sub) => {
    if (!window.confirm(`Remove ${sub.email} from the newsletter?`)) return;
    try {
      await api.delete(`/admin/newsletter/${sub.id}`);
      toast.success("Subscriber removed");
      load();
    } catch {
      toast.error("Delete failed");
    }
  };

  return (
    <div data-testid="newsletter-admin" className="border border-gray-border bg-surface p-5 mb-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Mail className="w-4 h-4 text-forest" />
          <span className="font-barlow font-black uppercase text-lg tracking-tight">Newsletter subscribers</span>
          <span className="text-[11px] font-bold bg-forest/10 text-forest px-2 py-0.5" data-testid="newsletter-admin-total">{total}</span>
        </div>
        <button onClick={onClose} className="text-ink/55 hover:text-ink p-1" aria-label="Close" data-testid="newsletter-admin-close">
          <X className="w-4 h-4" />
        </button>
      </div>

      {loading ? (
        <div className="text-ink/55 py-6 text-sm">Loading…</div>
      ) : items.length === 0 ? (
        <div className="text-ink/55 py-6 text-sm">No subscribers yet — the signup box is live on the blog.</div>
      ) : (
        <div className="max-h-80 overflow-y-auto divide-y divide-gray-border">
          {items.map((s) => (
            <div key={s.id} className="flex items-center justify-between py-2.5" data-testid={`newsletter-admin-row-${s.id}`}>
              <div>
                <div className="text-sm font-bold text-ink">{s.email}</div>
                <div className="text-[11px] text-ink/50">{(s.created_at || "").split("T")[0]} · via {s.source || "blog"}</div>
              </div>
              <button
                onClick={() => remove(s)}
                data-testid={`newsletter-admin-delete-${s.id}`}
                className="text-red-400 hover:bg-red-400 hover:text-white p-2 transition-colors"
                title="Remove"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
