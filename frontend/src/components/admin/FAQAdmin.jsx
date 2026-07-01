/**
 * FAQAdmin.jsx — CMS panel for landing-page Common Questions.
 *
 * Full CRUD against /api/admin/faq — admin can:
 *   - Add new questions (via "+ Add question" button at top)
 *   - Edit question or answer inline (auto-save on blur)
 *   - Toggle published / draft
 *   - Delete
 *   - Reorder up/down (updates order field, persists via /admin/faq/reorder)
 *
 * Renders exclusively for admins. Uses toast for feedback.
 */
import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  HelpCircle, Loader2, Plus, Trash2, Save, ChevronUp, ChevronDown,
  Eye, EyeOff, AlertCircle, RefreshCw,
} from "lucide-react";

import api from "@/lib/api";

const PRICE_SENTINEL = "__PRICE_FAQ__";

export default function FAQAdmin() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState({}); // { [id]: "save" | "delete" | "toggle" }
  // Local edit-buffer keyed by id — lets admin type without every keystroke
  // firing a PUT. Saved on blur or explicit Save click.
  const [drafts, setDrafts] = useState({}); // { [id]: { q, a } }
  const [newDraft, setNewDraft] = useState({ q: "", a: "" });

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/admin/faq");
      setItems(Array.isArray(data?.items) ? data.items : []);
      setDrafts({}); // clear pending drafts on reload
    } catch (err) {
      toast.error("Failed to load FAQ items");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const draftOf = (item) => drafts[item.id] || { q: item.q, a: item.a };
  const isDirty = (item) => {
    const d = drafts[item.id];
    if (!d) return false;
    return d.q !== item.q || d.a !== item.a;
  };
  const setDraftField = (id, field, value) => {
    setDrafts((s) => ({ ...s, [id]: { ...(s[id] || {}), [field]: value } }));
  };

  const saveItem = async (item) => {
    const d = draftOf(item);
    const patch = {};
    if (d.q !== item.q) patch.q = d.q;
    if (d.a !== item.a) patch.a = d.a;
    if (Object.keys(patch).length === 0) return;
    setBusy((s) => ({ ...s, [item.id]: "save" }));
    try {
      const { data } = await api.put(`/admin/faq/${item.id}`, patch);
      setItems((s) => s.map((i) => (i.id === item.id ? data : i)));
      setDrafts((s) => {
        const next = { ...s };
        delete next[item.id];
        return next;
      });
      toast.success("Saved");
    } catch (err) {
      const detail = err?.response?.data?.detail || "Could not save";
      toast.error(String(detail));
    } finally {
      setBusy((s) => ({ ...s, [item.id]: null }));
    }
  };

  const togglePublished = async (item) => {
    setBusy((s) => ({ ...s, [item.id]: "toggle" }));
    try {
      const { data } = await api.put(`/admin/faq/${item.id}`, { published: !item.published });
      setItems((s) => s.map((i) => (i.id === item.id ? data : i)));
      toast.success(data.published ? "Published" : "Hidden from site");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not update");
    } finally {
      setBusy((s) => ({ ...s, [item.id]: null }));
    }
  };

  const deleteItem = async (item) => {
    if (!window.confirm(`Delete this question?\n\n"${item.q}"`)) return;
    setBusy((s) => ({ ...s, [item.id]: "delete" }));
    try {
      await api.delete(`/admin/faq/${item.id}`);
      setItems((s) => s.filter((i) => i.id !== item.id));
      toast.success("Deleted");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not delete");
    } finally {
      setBusy((s) => ({ ...s, [item.id]: null }));
    }
  };

  const move = async (item, direction) => {
    const idx = items.findIndex((i) => i.id === item.id);
    if (idx < 0) return;
    const nextIdx = direction === "up" ? idx - 1 : idx + 1;
    if (nextIdx < 0 || nextIdx >= items.length) return;
    // Optimistic swap
    const reordered = [...items];
    [reordered[idx], reordered[nextIdx]] = [reordered[nextIdx], reordered[idx]];
    setItems(reordered);
    try {
      const ordered_ids = reordered.map((i) => i.id);
      await api.post("/admin/faq/reorder", { ordered_ids });
    } catch (err) {
      toast.error("Could not reorder — reloading");
      load();
    }
  };

  const createNew = async () => {
    const q = newDraft.q.trim();
    const a = newDraft.a.trim();
    if (!q || !a) {
      toast.error("Both question and answer are required");
      return;
    }
    setCreating(true);
    try {
      const { data } = await api.post("/admin/faq", { q, a });
      setItems((s) => [...s, data]);
      setNewDraft({ q: "", a: "" });
      toast.success("Question added — now live on the landing page");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not create");
    } finally {
      setCreating(false);
    }
  };

  if (loading) {
    return (
      <div className="py-12 text-center" data-testid="faq-admin-loading">
        <Loader2 className="w-8 h-8 text-forest mx-auto animate-spin" />
        <p className="mt-3 text-sm text-ink/60">Loading FAQ items...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="faq-admin">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <HelpCircle className="w-4 h-4 text-volt" />
            <span className="text-volt text-[10px] uppercase tracking-[0.22em] font-bold">CMS · Landing FAQ</span>
          </div>
          <h2 className="font-barlow font-black uppercase text-2xl md:text-3xl text-ink leading-tight">
            Common Questions
          </h2>
          <p className="mt-2 text-sm text-ink/65 max-w-2xl leading-relaxed">
            Edit, reorder, add, or remove questions shown in the landing page&apos;s FAQ block. Changes go live immediately &mdash; no deploy needed. Use{" "}
            <code className="text-forest font-bold bg-forest/8 px-1.5 py-0.5">{PRICE_SENTINEL}</code>{" "}
            as the answer to render the dynamic pricing copy.
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          data-testid="faq-admin-refresh"
          className="inline-flex items-center gap-1.5 text-[10px] uppercase tracking-widest font-bold text-ink/50 hover:text-forest px-3 py-2 border border-gray-border hover:border-forest transition-colors"
        >
          <RefreshCw className="w-3 h-3" /> Refresh
        </button>
      </div>

      {/* ── Add-new form ──────────────────────────────────────────────── */}
      <div className="bg-surface border border-gray-border p-5 md:p-6" data-testid="faq-admin-create-card">
        <div className="text-[10px] uppercase tracking-[0.28em] font-black text-forest mb-3 flex items-center gap-1.5">
          <Plus className="w-3.5 h-3.5" /> Add new question
        </div>
        <div className="space-y-3">
          <input
            type="text"
            placeholder="Question (e.g. Do you offer refunds?)"
            maxLength={300}
            value={newDraft.q}
            onChange={(e) => setNewDraft((s) => ({ ...s, q: e.target.value }))}
            data-testid="faq-admin-new-q"
            className="w-full bg-deepnavy border border-gray-border px-3 py-2.5 text-ink font-semibold focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
          />
          <textarea
            placeholder="Honest, complete answer... (up to 5000 chars)"
            maxLength={5000}
            rows={4}
            value={newDraft.a}
            onChange={(e) => setNewDraft((s) => ({ ...s, a: e.target.value }))}
            data-testid="faq-admin-new-a"
            className="w-full bg-deepnavy border border-gray-border px-3 py-2.5 text-ink text-sm leading-relaxed focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt resize-y"
          />
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <span className="text-[10px] text-ink/45">
              {newDraft.q.length}/300 · {newDraft.a.length}/5000
            </span>
            <button
              type="button"
              onClick={createNew}
              disabled={creating || !newDraft.q.trim() || !newDraft.a.trim()}
              data-testid="faq-admin-create-btn"
              className="bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-5 py-2.5 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              Add question
            </button>
          </div>
        </div>
      </div>

      {/* ── Items list ────────────────────────────────────────────────── */}
      {items.length === 0 ? (
        <div className="border border-gray-border bg-cream-card p-8 text-center">
          <AlertCircle className="w-10 h-10 text-ink/30 mx-auto mb-3" />
          <p className="text-sm text-ink/55">No FAQ items yet. Add your first question above.</p>
        </div>
      ) : (
        <div className="space-y-3" data-testid="faq-admin-list">
          {items.map((item, idx) => {
            const d = draftOf(item);
            const dirty = isDirty(item);
            const b = busy[item.id];
            const isPriceFaq = item.a === PRICE_SENTINEL;
            return (
              <div
                key={item.id}
                data-testid={`faq-admin-row-${idx}`}
                className={`border ${item.published ? "border-gray-border" : "border-orange-300/40 bg-orange-50/40"} bg-surface p-4 md:p-5 space-y-3`}
              >
                {/* Row header — order + published + delete */}
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] uppercase tracking-[0.24em] font-black text-ink/40 tabular-nums">
                      #{String(idx + 1).padStart(2, "0")}
                    </span>
                    {!item.published && (
                      <span className="inline-flex items-center gap-1 text-[9px] uppercase tracking-widest font-black text-orange-500 border border-orange-400/40 bg-orange-400/10 px-1.5 py-0.5">
                        <EyeOff className="w-2.5 h-2.5" /> Draft
                      </span>
                    )}
                    {isPriceFaq && (
                      <span className="inline-flex items-center gap-1 text-[9px] uppercase tracking-widest font-black text-forest border border-forest/40 bg-forest/8 px-1.5 py-0.5">
                        Dynamic pricing
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => move(item, "up")}
                      disabled={idx === 0}
                      data-testid={`faq-admin-move-up-${idx}`}
                      className="w-8 h-8 flex items-center justify-center border border-gray-border hover:border-forest hover:text-forest transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                      title="Move up"
                    >
                      <ChevronUp className="w-4 h-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => move(item, "down")}
                      disabled={idx === items.length - 1}
                      data-testid={`faq-admin-move-down-${idx}`}
                      className="w-8 h-8 flex items-center justify-center border border-gray-border hover:border-forest hover:text-forest transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                      title="Move down"
                    >
                      <ChevronDown className="w-4 h-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => togglePublished(item)}
                      disabled={b === "toggle"}
                      data-testid={`faq-admin-toggle-${idx}`}
                      className={`h-8 px-3 flex items-center gap-1.5 text-[10px] uppercase tracking-widest font-black border transition-colors ${
                        item.published
                          ? "border-forest text-forest hover:bg-forest hover:text-white"
                          : "border-orange-400 text-orange-500 hover:bg-orange-400 hover:text-white"
                      } disabled:opacity-50`}
                      title={item.published ? "Hide from site" : "Publish"}
                    >
                      {b === "toggle" ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : item.published ? (
                        <><Eye className="w-3 h-3" /> Published</>
                      ) : (
                        <><EyeOff className="w-3 h-3" /> Draft</>
                      )}
                    </button>
                    <button
                      type="button"
                      onClick={() => deleteItem(item)}
                      disabled={b === "delete"}
                      data-testid={`faq-admin-delete-${idx}`}
                      className="w-8 h-8 flex items-center justify-center border border-red-300/50 text-red-500 hover:bg-red-500 hover:text-white transition-colors disabled:opacity-50"
                      title="Delete"
                    >
                      {b === "delete" ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                </div>

                {/* Question input */}
                <input
                  type="text"
                  value={d.q}
                  maxLength={300}
                  onChange={(e) => setDraftField(item.id, "q", e.target.value)}
                  onBlur={() => dirty && saveItem(item)}
                  data-testid={`faq-admin-q-${idx}`}
                  className="w-full bg-cream-card border border-gray-border px-3 py-2 text-ink font-bold focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
                  placeholder="Question..."
                />

                {/* Answer textarea */}
                <textarea
                  value={d.a}
                  maxLength={5000}
                  rows={Math.min(8, Math.max(3, Math.ceil((d.a?.length || 0) / 90)))}
                  onChange={(e) => setDraftField(item.id, "a", e.target.value)}
                  onBlur={() => dirty && saveItem(item)}
                  data-testid={`faq-admin-a-${idx}`}
                  className="w-full bg-cream-card border border-gray-border px-3 py-2 text-ink text-sm leading-relaxed focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt resize-y font-mono-ish"
                  placeholder="Answer..."
                />

                {/* Save row (only when dirty) */}
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <span className="text-[10px] text-ink/40">
                    {(d.q || "").length}/300 · {(d.a || "").length}/5000
                    {dirty && <span className="ml-2 text-orange-500 font-bold">· UNSAVED</span>}
                  </span>
                  {dirty && (
                    <button
                      type="button"
                      onClick={() => saveItem(item)}
                      disabled={b === "save"}
                      data-testid={`faq-admin-save-${idx}`}
                      className="inline-flex items-center gap-1.5 bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-xs px-4 py-2 transition-colors disabled:opacity-50"
                    >
                      {b === "save" ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                      Save
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <p className="mt-4 text-[11px] text-ink/45 leading-relaxed">
        <strong className="text-ink/60">Tip:</strong> Question edits auto-save when you click away from the field.
        Toggle a question to <strong>Draft</strong> to hide it from the public site without deleting.
        The <code className="text-forest font-bold bg-forest/8 px-1 py-0.5">{PRICE_SENTINEL}</code> sentinel is replaced
        by the live pricing paragraph on the landing page.
      </p>
    </div>
  );
}
