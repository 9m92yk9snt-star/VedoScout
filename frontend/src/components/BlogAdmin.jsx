import React, { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Plus, Edit3, Trash2, Eye, FileText, Sparkles, Save, Send, Upload, Loader2, X,
  ImageIcon, Tag as TagIcon, ArrowLeft,
} from "lucide-react";
import api from "@/lib/api";

const STATUS_LABEL = { draft: "Draft", published: "Live" };

/* ─────────────────────────────────────────────────────────────────────── */
/* Top-level Blog admin: list + open editor                                */
/* ─────────────────────────────────────────────────────────────────────── */
export default function BlogAdmin() {
  const [view, setView] = useState({ kind: "list" }); // {kind:"list"} | {kind:"edit", id?}

  if (view.kind === "edit") {
    return (
      <BlogEditor
        postId={view.id}
        onClose={() => setView({ kind: "list" })}
      />
    );
  }
  return <BlogList onNew={() => setView({ kind: "edit" })} onEdit={(id) => setView({ kind: "edit", id })} />;
}

/* ─────────────────────────────────────────────────────────────────────── */
/* Blog list                                                                */
/* ─────────────────────────────────────────────────────────────────────── */
function BlogList({ onNew, onEdit }) {
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.get("/blog/admin/posts");
      setPosts(res.data?.items || []);
    } catch (e) {
      toast.error("Failed to load posts: " + (e?.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleDelete = async (post) => {
    if (!window.confirm(`Delete "${post.title}"? This cannot be undone.`)) return;
    try {
      await api.delete(`/blog/admin/posts/${post.id}`);
      toast.success("Post deleted");
      load();
    } catch (e) {
      toast.error("Delete failed: " + (e?.response?.data?.detail || e.message));
    }
  };

  return (
    <div data-testid="admin-blog-list">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-6">
        <div>
          <h2 className="font-barlow font-black uppercase text-2xl md:text-3xl tracking-tight">Blog</h2>
          <p className="text-sm text-ink/60 mt-1">SEO-optimised articles. AI drafting + Gemini SEO suggestions available.</p>
        </div>
        <button
          onClick={onNew}
          data-testid="admin-blog-new-btn"
          className="bg-volt hover:bg-volt-hover text-white font-barlow font-black uppercase tracking-widest text-xs px-5 py-3 flex items-center gap-2 transition-colors w-fit"
        >
          <Plus className="w-4 h-4" /> New post
        </button>
      </div>

      {loading ? (
        <div className="text-ink/55 py-10">Loading posts…</div>
      ) : posts.length === 0 ? (
        <div className="border border-gray-border bg-surface p-10 text-center">
          <FileText className="w-10 h-10 text-ink/30 mx-auto" />
          <h3 className="mt-4 font-barlow font-black uppercase text-xl text-ink">No posts yet</h3>
          <p className="mt-2 text-sm text-ink/60">Write your first SEO article — or let Gemini draft it for you in seconds.</p>
          <button
            onClick={onNew}
            className="mt-5 bg-volt hover:bg-volt-hover text-white font-barlow font-black uppercase tracking-widest text-xs px-5 py-3 inline-flex items-center gap-2"
          >
            <Sparkles className="w-4 h-4" /> Start writing
          </button>
        </div>
      ) : (
        <div className="border border-gray-border bg-surface overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-cream-soft border-b border-gray-border">
              <tr className="text-left">
                <th className="p-3 text-[10px] uppercase tracking-widest font-bold text-ink/55">Title</th>
                <th className="p-3 text-[10px] uppercase tracking-widest font-bold text-ink/55">Category</th>
                <th className="p-3 text-[10px] uppercase tracking-widest font-bold text-ink/55">Status</th>
                <th className="p-3 text-[10px] uppercase tracking-widest font-bold text-ink/55">Views</th>
                <th className="p-3 text-[10px] uppercase tracking-widest font-bold text-ink/55">Updated</th>
                <th className="p-3 text-right text-[10px] uppercase tracking-widest font-bold text-ink/55">Actions</th>
              </tr>
            </thead>
            <tbody>
              {posts.map((p) => (
                <tr key={p.id} className="border-b border-gray-border last:border-0 hover:bg-cream-soft/40">
                  <td className="p-3">
                    <div className="font-bold text-ink">{p.title}</div>
                    <div className="text-xs text-ink/55 mt-0.5">/{p.slug}</div>
                  </td>
                  <td className="p-3 text-ink/70">{p.category || "—"}</td>
                  <td className="p-3">
                    <span className={`px-2 py-1 text-[10px] uppercase tracking-widest font-bold ${
                      p.status === "published" ? "bg-volt/10 text-volt-hover" : "bg-ink/5 text-ink/55"
                    }`}>
                      {STATUS_LABEL[p.status] || p.status}
                    </span>
                  </td>
                  <td className="p-3 text-ink/70">{p.view_count || 0}</td>
                  <td className="p-3 text-ink/55 text-xs">{p.updated_at?.split("T")[0]}</td>
                  <td className="p-3 text-right">
                    <div className="flex gap-2 justify-end">
                      {p.status === "published" && (
                        <a
                          href={`/blog/${p.slug}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          data-testid={`admin-blog-view-${p.id}`}
                          title="View live"
                          className="text-ink/60 hover:bg-forest hover:text-cream-card p-2 transition-colors"
                        >
                          <Eye className="w-4 h-4" />
                        </a>
                      )}
                      <button
                        onClick={() => onEdit(p.id)}
                        data-testid={`admin-blog-edit-${p.id}`}
                        title="Edit"
                        className="text-volt hover:bg-volt hover:text-white p-2 transition-colors"
                      >
                        <Edit3 className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleDelete(p)}
                        data-testid={`admin-blog-delete-${p.id}`}
                        title="Delete"
                        className="text-red-400 hover:bg-red-400 hover:text-ink p-2 transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */
/* Blog editor                                                              */
/* ─────────────────────────────────────────────────────────────────────── */
function BlogEditor({ postId, onClose }) {
  const isNew = !postId;
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [seoBusy, setSeoBusy] = useState(false);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [aiTopic, setAiTopic] = useState("");
  const [aiKeyword, setAiKeyword] = useState("");
  const [categories, setCategories] = useState([]);
  const fileInputRef = useRef(null);

  const [form, setForm] = useState({
    title: "",
    subtitle: "",
    slug: "",
    content_md: "",
    excerpt: "",
    cover_image_url: "",
    cover_image_alt: "",
    category: "",
    tags: "",
    author_name: "ScoutMePlay Editorial",
    status: "draft",
    meta_title: "",
    meta_description: "",
    meta_keywords: "",
  });

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e?.target?.value ?? e }));

  // Load
  useEffect(() => {
    const init = async () => {
      try {
        const catsRes = await api.get("/blog/categories");
        setCategories(catsRes.data || []);
      } catch {
        /* categories optional */
      }
      if (!isNew) {
        try {
          const r = await api.get(`/blog/admin/posts/${postId}`);
          const p = r.data || {};
          setForm({
            title: p.title || "",
            subtitle: p.subtitle || "",
            slug: p.slug || "",
            content_md: p.content_md || "",
            excerpt: p.excerpt || "",
            cover_image_url: p.cover_image_url || "",
            cover_image_alt: p.cover_image_alt || "",
            category: p.category || "",
            tags: (p.tags || []).join(", "),
            author_name: p.author_name || "ScoutMePlay Editorial",
            status: p.status || "draft",
            meta_title: p.meta_title || "",
            meta_description: p.meta_description || "",
            meta_keywords: (p.meta_keywords || []).join(", "),
          });
        } catch (e) {
          toast.error("Failed to load post");
        }
      }
      setLoading(false);
    };
    init();
  }, [postId, isNew]);

  const save = async (status = form.status) => {
    if (!form.title.trim()) {
      toast.error("Title is required");
      return;
    }
    if (!form.content_md.trim()) {
      toast.error("Content is required");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        title: form.title,
        subtitle: form.subtitle || null,
        slug: form.slug || null,
        content_md: form.content_md,
        excerpt: form.excerpt || null,
        cover_image_url: form.cover_image_url || null,
        cover_image_alt: form.cover_image_alt || null,
        category: form.category || null,
        tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
        author_name: form.author_name || null,
        status,
        meta_title: form.meta_title || null,
        meta_description: form.meta_description || null,
        meta_keywords: form.meta_keywords.split(",").map((t) => t.trim()).filter(Boolean),
      };
      if (isNew) {
        const r = await api.post("/blog/admin/posts", payload);
        toast.success(status === "published" ? "Article published" : "Draft saved");
        onClose();
        return r;
      } else {
        await api.put(`/blog/admin/posts/${postId}`, payload);
        toast.success(status === "published" ? "Article published" : "Draft saved");
        onClose();
      }
    } catch (e) {
      toast.error("Save failed: " + (e?.response?.data?.detail || e.message));
    } finally {
      setSaving(false);
    }
  };

  const aiDraft = async () => {
    if (!aiTopic.trim()) {
      toast.error("Type a topic first");
      return;
    }
    setAiBusy(true);
    try {
      const r = await api.post("/blog/admin/ai/draft", {
        topic: aiTopic.trim(),
        target_keyword: aiKeyword.trim() || null,
      });
      setForm((f) => ({
        ...f,
        title: r.data.title || f.title,
        content_md: r.data.content_md || f.content_md,
        excerpt: r.data.excerpt || f.excerpt,
      }));
      toast.success("Draft inserted — edit freely then click 'Suggest SEO'");
    } catch (e) {
      toast.error("AI draft failed: " + (e?.response?.data?.detail || e.message));
    } finally {
      setAiBusy(false);
    }
  };

  const aiSeo = async () => {
    if (!form.title || !form.content_md) {
      toast.error("Need title + content for SEO suggestions");
      return;
    }
    setSeoBusy(true);
    try {
      const r = await api.post("/blog/admin/ai/seo", {
        title: form.title,
        content_md: form.content_md,
      });
      setForm((f) => ({
        ...f,
        meta_title: r.data.meta_title || f.meta_title,
        meta_description: r.data.meta_description || f.meta_description,
        meta_keywords: (r.data.meta_keywords || []).join(", "),
      }));
      toast.success("Meta title, description and keywords suggested by Gemini");
    } catch (e) {
      toast.error("SEO suggestion failed: " + (e?.response?.data?.detail || e.message));
    } finally {
      setSeoBusy(false);
    }
  };

  const onUpload = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 5 * 1024 * 1024) {
      toast.error("Image too large (max 5 MB)");
      return;
    }
    setUploadBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const r = await api.post("/blog/admin/upload-image", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setForm((s) => ({ ...s, cover_image_url: r.data.url }));
      toast.success("Image uploaded");
    } catch (err) {
      toast.error("Upload failed: " + (err?.response?.data?.detail || err.message));
    } finally {
      setUploadBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  if (loading) {
    return <div className="text-ink/55 py-10">Loading editor…</div>;
  }

  return (
    <div data-testid="admin-blog-editor" className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div className="flex items-center gap-3">
          <button onClick={onClose} className="text-ink/55 hover:text-ink flex items-center gap-1.5 text-xs uppercase tracking-widest font-bold">
            <ArrowLeft className="w-3.5 h-3.5" /> Back
          </button>
          <h2 className="font-barlow font-black uppercase text-2xl tracking-tight">
            {isNew ? "New article" : "Edit article"}
          </h2>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => setShowPreview((v) => !v)}
            data-testid="admin-blog-toggle-preview"
            className="text-xs uppercase tracking-widest font-bold text-ink/65 hover:text-ink border border-gray-border hover:border-forest px-4 py-2.5 transition-colors flex items-center gap-2"
          >
            <Eye className="w-3.5 h-3.5" /> {showPreview ? "Hide preview" : "Preview"}
          </button>
          <button
            onClick={() => save("draft")}
            disabled={saving}
            data-testid="admin-blog-save-draft"
            className="text-xs uppercase tracking-widest font-bold border border-gray-border hover:border-forest px-4 py-2.5 transition-colors flex items-center gap-2 disabled:opacity-50"
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
            Save draft
          </button>
          <button
            onClick={() => save("published")}
            disabled={saving}
            data-testid="admin-blog-publish"
            className="bg-volt hover:bg-volt-hover text-white font-barlow font-black uppercase tracking-widest text-xs px-5 py-2.5 flex items-center gap-2 transition-colors disabled:opacity-50"
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
            Publish
          </button>
        </div>
      </div>

      {/* AI draft card */}
      <div className="border border-volt/40 bg-volt/5 p-5">
        <div className="flex items-center gap-2 mb-3">
          <Sparkles className="w-4 h-4 text-volt-hover" />
          <span className="text-[10px] uppercase tracking-[0.25em] font-bold text-volt-hover">AI Draft Assist</span>
        </div>
        <p className="text-sm text-ink/70 mb-3">Paste a topic and a primary keyword. Gemini will draft a Markdown article you can edit below.</p>
        <div className="grid md:grid-cols-[1fr_240px_auto] gap-2">
          <input
            data-testid="admin-blog-ai-topic"
            value={aiTopic}
            onChange={(e) => setAiTopic(e.target.value)}
            placeholder="Topic — e.g. How U13 attacking midfielders can train decision-making"
            className="px-3 py-2.5 bg-surface border border-gray-border focus:border-forest outline-none text-sm"
          />
          <input
            data-testid="admin-blog-ai-keyword"
            value={aiKeyword}
            onChange={(e) => setAiKeyword(e.target.value)}
            placeholder="Primary keyword (optional)"
            className="px-3 py-2.5 bg-surface border border-gray-border focus:border-forest outline-none text-sm"
          />
          <button
            onClick={aiDraft}
            disabled={aiBusy}
            data-testid="admin-blog-ai-draft"
            className="bg-volt hover:bg-volt-hover text-white font-barlow font-black uppercase tracking-widest text-xs px-5 py-2.5 flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {aiBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
            Draft
          </button>
        </div>
      </div>

      {/* Form */}
      <div className="grid lg:grid-cols-[1fr_320px] gap-6">
        {/* LEFT — main form */}
        <div className="space-y-4">
          <FieldLabel>Title</FieldLabel>
          <input
            data-testid="admin-blog-title"
            value={form.title}
            onChange={set("title")}
            placeholder="Article headline (max 100 chars)"
            className="w-full px-4 py-3 bg-surface border border-gray-border focus:border-forest outline-none text-lg font-bold"
          />

          <FieldLabel>Subtitle (optional, italic dek)</FieldLabel>
          <input
            data-testid="admin-blog-subtitle"
            value={form.subtitle}
            onChange={set("subtitle")}
            placeholder="A 1-line hook below the title"
            className="w-full px-4 py-2.5 bg-surface border border-gray-border focus:border-forest outline-none text-sm"
          />

          <FieldLabel>Slug (auto-generated from title if empty)</FieldLabel>
          <input
            data-testid="admin-blog-slug"
            value={form.slug}
            onChange={set("slug")}
            placeholder="my-article-slug"
            className="w-full px-4 py-2.5 bg-surface border border-gray-border focus:border-forest outline-none text-sm font-mono"
          />

          <FieldLabel>Content (Markdown)</FieldLabel>
          <div className={`grid gap-3 ${showPreview ? "lg:grid-cols-2" : ""}`}>
            <textarea
              data-testid="admin-blog-content"
              value={form.content_md}
              onChange={set("content_md")}
              placeholder={"# Title\n\nWrite in Markdown. Use ## for sections, **bold**, *italics*, > for quotes, - for lists."}
              rows={26}
              className="w-full px-4 py-3 bg-surface border border-gray-border focus:border-forest outline-none text-sm font-mono leading-relaxed resize-y"
              spellCheck
            />
            {showPreview && (
              <div className="bg-cream-soft/40 border border-gray-border p-5 overflow-y-auto max-h-[700px]">
                <div className="prose prose-stone max-w-none prose-headings:font-barlow prose-headings:uppercase prose-h1:text-3xl prose-h2:text-xl prose-h2:mt-6 prose-blockquote:border-forest prose-a:text-forest">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {form.content_md || "_Preview will appear here…_"}
                  </ReactMarkdown>
                </div>
              </div>
            )}
          </div>

          <FieldLabel>Excerpt (≤ 220 chars, auto-generated if empty)</FieldLabel>
          <textarea
            data-testid="admin-blog-excerpt"
            value={form.excerpt}
            onChange={set("excerpt")}
            rows={2}
            placeholder="Short summary that shows on blog index cards"
            className="w-full px-4 py-2.5 bg-surface border border-gray-border focus:border-forest outline-none text-sm resize-y"
          />
        </div>

        {/* RIGHT — sidebar */}
        <aside className="space-y-5">
          <SidebarCard title="Status">
            <div className="text-xs uppercase tracking-widest font-bold text-ink/70 mt-1">
              {STATUS_LABEL[form.status]}
            </div>
            <p className="text-xs text-ink/55 mt-2">Click <b>Publish</b> to make this article live and SEO-indexed.</p>
          </SidebarCard>

          <SidebarCard title="Cover image">
            {form.cover_image_url ? (
              <div className="space-y-2">
                <img src={form.cover_image_url} alt="" className="w-full aspect-[16/9] object-cover bg-cream-soft" />
                <button
                  onClick={() => setForm((s) => ({ ...s, cover_image_url: "" }))}
                  className="text-xs uppercase tracking-widest font-bold text-red-500 hover:underline flex items-center gap-1"
                >
                  <X className="w-3 h-3" /> Remove
                </button>
              </div>
            ) : (
              <div className="aspect-[16/9] border border-dashed border-gray-border bg-cream-soft/40 flex items-center justify-center text-ink/40">
                <ImageIcon className="w-8 h-8" />
              </div>
            )}
            <input
              data-testid="admin-blog-cover-url"
              value={form.cover_image_url}
              onChange={set("cover_image_url")}
              placeholder="Paste image URL"
              className="mt-3 w-full px-3 py-2 bg-surface border border-gray-border focus:border-forest outline-none text-xs font-mono"
            />
            <div className="mt-2 flex items-center gap-2">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp,image/gif"
                onChange={onUpload}
                className="hidden"
                data-testid="admin-blog-cover-file"
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={uploadBusy}
                className="text-xs uppercase tracking-widest font-bold border border-gray-border hover:border-forest px-3 py-2 flex items-center gap-2 disabled:opacity-50"
              >
                {uploadBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
                Upload
              </button>
            </div>
            <input
              data-testid="admin-blog-cover-alt"
              value={form.cover_image_alt}
              onChange={set("cover_image_alt")}
              placeholder="Image alt text (accessibility + SEO)"
              className="mt-2 w-full px-3 py-2 bg-surface border border-gray-border focus:border-forest outline-none text-xs"
            />
          </SidebarCard>

          <SidebarCard title="Taxonomy">
            <FieldLabel>Category</FieldLabel>
            <select
              data-testid="admin-blog-category"
              value={form.category}
              onChange={set("category")}
              className="w-full px-3 py-2 bg-surface border border-gray-border focus:border-forest outline-none text-sm"
            >
              <option value="">(none)</option>
              {categories.map((c) => (
                <option key={c.id} value={c.name}>{c.name}</option>
              ))}
            </select>

            <FieldLabel className="mt-3">Tags (comma separated)</FieldLabel>
            <input
              data-testid="admin-blog-tags"
              value={form.tags}
              onChange={set("tags")}
              placeholder="U14, scouting, parents"
              className="w-full px-3 py-2 bg-surface border border-gray-border focus:border-forest outline-none text-sm"
            />
          </SidebarCard>

          <SidebarCard title="Author">
            <input
              data-testid="admin-blog-author"
              value={form.author_name}
              onChange={set("author_name")}
              className="w-full px-3 py-2 bg-surface border border-gray-border focus:border-forest outline-none text-sm"
            />
          </SidebarCard>

          <SidebarCard
            title="SEO"
            action={
              <button
                onClick={aiSeo}
                disabled={seoBusy}
                data-testid="admin-blog-ai-seo"
                className="text-[10px] uppercase tracking-[0.2em] font-bold text-volt-hover hover:text-forest flex items-center gap-1 disabled:opacity-50"
              >
                {seoBusy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
                AI suggest
              </button>
            }
          >
            <FieldLabel>Meta title (≤ 60 chars ideal)</FieldLabel>
            <input
              data-testid="admin-blog-meta-title"
              value={form.meta_title}
              onChange={set("meta_title")}
              placeholder="Falls back to article title"
              className="w-full px-3 py-2 bg-surface border border-gray-border focus:border-forest outline-none text-sm"
            />
            <div className={`text-[10px] mt-1 ${form.meta_title.length > 70 ? "text-red-500" : "text-ink/45"}`}>
              {form.meta_title.length} / 60–70
            </div>

            <FieldLabel className="mt-3">Meta description (≤ 160 chars)</FieldLabel>
            <textarea
              data-testid="admin-blog-meta-description"
              value={form.meta_description}
              onChange={set("meta_description")}
              rows={3}
              placeholder="Click-worthy summary that shows in Google results"
              className="w-full px-3 py-2 bg-surface border border-gray-border focus:border-forest outline-none text-sm resize-y"
            />
            <div className={`text-[10px] mt-1 ${form.meta_description.length > 160 ? "text-red-500" : "text-ink/45"}`}>
              {form.meta_description.length} / 160
            </div>

            <FieldLabel className="mt-3">Meta keywords (comma separated)</FieldLabel>
            <input
              data-testid="admin-blog-meta-keywords"
              value={form.meta_keywords}
              onChange={set("meta_keywords")}
              placeholder="football scouting, U14, training"
              className="w-full px-3 py-2 bg-surface border border-gray-border focus:border-forest outline-none text-sm"
            />
          </SidebarCard>
        </aside>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */
function FieldLabel({ children, className = "" }) {
  return (
    <label className={`block text-[10px] uppercase tracking-[0.22em] font-bold text-ink/55 mb-1.5 ${className}`}>
      {children}
    </label>
  );
}

function SidebarCard({ title, children, action }) {
  return (
    <div className="border border-gray-border bg-surface p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] uppercase tracking-[0.25em] font-bold text-ink/55">{title}</span>
        {action}
      </div>
      {children}
    </div>
  );
}
