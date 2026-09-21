import React, { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { Search, Clock, ArrowRight, Tag as TagIcon } from "lucide-react";
import Navigation from "@/components/Navigation";
import SEO, { organizationJsonLd } from "@/components/SEO";
import NewsletterSignup from "@/components/NewsletterSignup";
import BlogCtaBanner from "@/components/BlogCtaBanner";
import api from "@/lib/api";

const LIME = "#ccff00";

function formatDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
  } catch {
    return "";
  }
}

function PostCard({ post, featured = false }) {
  const img = post.cover_image_url;
  return (
    <Link
      to={`/blog/${post.slug}`}
      data-testid={`blog-card-${post.slug}`}
      className={`group block relative bg-surface border border-gray-border hover:border-forest-pop transition-all duration-300 overflow-hidden hover:-translate-y-1 ${
        featured ? "md:col-span-2 md:row-span-2" : ""
      }`}
    >
      <div className={`relative overflow-hidden bg-cream-soft ${featured ? "aspect-[16/10]" : "aspect-[16/9]"}`}>
        {img ? (
          <img
            src={img}
            alt={post.cover_image_alt || post.title}
            className="absolute inset-0 w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
            loading="lazy"
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center bg-gradient-to-br from-forest to-forest-pop">
            <span className="font-barlow font-black uppercase text-cream-card text-2xl tracking-widest opacity-80">
              SCOUT<span style={{ color: LIME }}>ME</span>PLAY
            </span>
          </div>
        )}
        {post.category && (
          <span
            className="absolute top-3 left-3 px-2.5 py-1 text-[10px] uppercase tracking-[0.2em] font-bold text-cream-card"
            style={{ background: "rgba(31,79,47,0.92)" }}
          >
            {post.category}
          </span>
        )}
      </div>
      <div className={`p-5 ${featured ? "md:p-8" : ""}`}>
        <h3
          className={`font-barlow font-black uppercase text-ink leading-tight tracking-tight group-hover:text-forest transition-colors ${
            featured ? "text-2xl md:text-3xl" : "text-lg"
          }`}
        >
          {post.title}
        </h3>
        {post.excerpt && (
          <p className={`mt-3 text-ink/65 leading-relaxed ${featured ? "text-base" : "text-sm"} line-clamp-3`}>
            {post.excerpt}
          </p>
        )}
        <div className="mt-5 pt-4 border-t border-gray-border flex items-center justify-between text-[10px] uppercase tracking-[0.18em] font-bold text-ink/55">
          <span>{formatDate(post.published_at)}</span>
          <span className="flex items-center gap-1.5">
            <Clock className="w-3 h-3" /> {post.reading_time_minutes || 5} min
          </span>
        </div>
      </div>
    </Link>
  );
}

export default function BlogIndexPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [posts, setPosts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState(searchParams.get("q") || "");

  const activeCategory = searchParams.get("category") || "";
  const activeTag = searchParams.get("tag") || "";
  const activeQuery = searchParams.get("q") || "";

  const fetchPosts = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (activeCategory) params.set("category", activeCategory);
      if (activeTag) params.set("tag", activeTag);
      if (activeQuery) params.set("q", activeQuery);
      params.set("limit", "24");
      const [postsRes, catsRes] = await Promise.all([
        api.get(`/blog/posts?${params.toString()}`),
        api.get(`/blog/categories`),
      ]);
      setPosts(postsRes.data?.items || []);
      setCategories(catsRes.data || []);
    } catch (e) {
      console.error("Blog load failed", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPosts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeCategory, activeTag, activeQuery]);

  const onSearchSubmit = (e) => {
    e.preventDefault();
    const next = new URLSearchParams(searchParams);
    if (searchTerm.trim()) next.set("q", searchTerm.trim());
    else next.delete("q");
    setSearchParams(next);
  };

  const setCategory = (slug) => {
    const next = new URLSearchParams(searchParams);
    if (!slug) next.delete("category");
    else next.set("category", slug);
    next.delete("tag");
    setSearchParams(next);
  };

  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const featured = posts[0];
  const rest = posts.slice(1);

  return (
    <div className="min-h-screen bg-cream-base text-ink">
      <SEO
        pageKey="blog"
        title="Blog — Football Scouting, Training & Pro Path Insights"
        description="Expert articles on football scouting, training drills, parent guides, and the academy-to-pro player path. Built for ambitious U7-U21 players, parents and coaches."
        url="/blog"
        type="website"
        jsonLd={organizationJsonLd(origin)}
      />
      <Navigation />

      {/* ===== HERO ===== */}
      <section className="relative pt-16 pb-12 md:pt-24 md:pb-16 border-b border-gray-border overflow-hidden">
        <div aria-hidden className="absolute -top-32 right-1/3 w-96 h-96 rounded-full pointer-events-none" style={{ background: `radial-gradient(circle, ${LIME}22, transparent 70%)` }} />
        <div className="max-w-6xl mx-auto px-6 md:px-10">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 border border-forest/30 bg-forest/5 mb-6">
            <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: LIME }} />
            <span className="text-[10px] uppercase tracking-[0.25em] font-bold text-forest">ScoutMePlay Journal</span>
          </div>
          <h1 className="font-barlow font-black uppercase text-5xl md:text-7xl lg:text-8xl text-ink leading-[0.92] tracking-tighter">
            The
            <span className="italic font-serif-italic text-forest font-normal lowercase ml-3">scouting</span>
            <br />
            playbook.
          </h1>
          <p className="mt-7 max-w-2xl text-ink/70 text-base md:text-lg leading-relaxed">
            Articles, tactics, and parent guides from coaches, scouts and analysts — written for ambitious U7–U21 players and the people around them.
          </p>

          {/* Search + categories */}
          <div className="mt-10 flex flex-col gap-5">
            <form onSubmit={onSearchSubmit} className="flex items-center gap-3 max-w-xl">
              <div className="relative flex-1">
                <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-ink/40" />
                <input
                  data-testid="blog-search-input"
                  type="text"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  placeholder="Search articles…"
                  className="w-full pl-10 pr-4 py-3 bg-surface border border-gray-border focus:border-forest outline-none text-sm font-medium transition-colors"
                />
              </div>
              <button
                type="submit"
                data-testid="blog-search-submit"
                className="bg-forest hover:bg-forest-pop text-cream-card font-barlow font-black uppercase tracking-widest text-xs px-5 py-3 transition-colors"
              >
                Search
              </button>
            </form>

            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={() => setCategory("")}
                data-testid="blog-cat-all"
                className={`px-3 py-1.5 text-[10px] uppercase tracking-[0.2em] font-bold transition-colors border ${
                  !activeCategory
                    ? "bg-forest text-cream-card border-forest"
                    : "bg-transparent text-ink/70 border-gray-border hover:border-forest hover:text-ink"
                }`}
              >
                All
              </button>
              {categories.map((c) => (
                <button
                  key={c.id}
                  onClick={() => setCategory(c.slug)}
                  data-testid={`blog-cat-${c.slug}`}
                  className={`px-3 py-1.5 text-[10px] uppercase tracking-[0.2em] font-bold transition-colors border ${
                    activeCategory === c.slug
                      ? "bg-forest text-cream-card border-forest"
                      : "bg-transparent text-ink/70 border-gray-border hover:border-forest hover:text-ink"
                  }`}
                >
                  {c.name}
                </button>
              ))}
            </div>
            {activeTag && (
              <div className="inline-flex items-center gap-2 text-xs text-ink/60">
                <TagIcon className="w-3 h-3" /> Filtering by tag:
                <span className="font-bold text-forest">#{activeTag}</span>
                <button onClick={() => { const n = new URLSearchParams(searchParams); n.delete("tag"); setSearchParams(n); }} className="underline">clear</button>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ===== POSTS GRID ===== */}
      <section className="max-w-6xl mx-auto px-6 md:px-10 py-14 md:py-20" data-testid="blog-grid">
        {loading ? (
          <div className="text-center text-ink/55 py-20">Loading articles…</div>
        ) : posts.length === 0 ? (
          <div className="text-center py-24">
            <h2 className="font-barlow font-black uppercase text-3xl tracking-tight text-ink/40">
              No articles yet
            </h2>
            <p className="mt-3 text-ink/55">Check back soon — we&apos;re publishing new pieces every week.</p>
          </div>
        ) : (
          <>
            <motion.div
              initial="hidden"
              animate="visible"
              variants={{ visible: { transition: { staggerChildren: 0.06 } } }}
              className="grid grid-cols-1 md:grid-cols-3 gap-5 md:gap-6 auto-rows-fr"
            >
              {featured && (
                <motion.div
                  variants={{ hidden: { opacity: 0, y: 18 }, visible: { opacity: 1, y: 0 } }}
                  transition={{ duration: 0.5 }}
                  className="md:col-span-2 md:row-span-2"
                >
                  <PostCard post={featured} featured />
                </motion.div>
              )}
              {rest.map((p) => (
                <motion.div
                  key={p.id}
                  variants={{ hidden: { opacity: 0, y: 18 }, visible: { opacity: 1, y: 0 } }}
                  transition={{ duration: 0.5 }}
                >
                  <PostCard post={p} />
                </motion.div>
              ))}
            </motion.div>
          </>
        )}
      </section>

      {/* ===== NEWSLETTER ===== */}
      <section className="max-w-6xl mx-auto px-6 md:px-10 pb-14 md:pb-20">
        <NewsletterSignup source="blog-index" />
      </section>

      {/* ===== CTA ===== */}
      <BlogCtaBanner source="index" />
    </div>
  );
}
