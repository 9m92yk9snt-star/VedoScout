import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Clock, ArrowLeft, ArrowRight, Tag as TagIcon, Calendar } from "lucide-react";
import Navigation from "@/components/Navigation";
import SEO, { articleJsonLd, breadcrumbJsonLd } from "@/components/SEO";
import BlogShareBar from "@/components/BlogShareBar";
import NewsletterSignup from "@/components/NewsletterSignup";
import api from "@/lib/api";

const LIME = "#ccff00";

function formatDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
  } catch {
    return "";
  }
}

export default function BlogArticlePage() {
  const { slug } = useParams();
  const [post, setPost] = useState(null);
  const [related, setRelated] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    api
      .get(`/blog/posts/${slug}`)
      .then((res) => {
        if (!active) return;
        setPost(res.data?.post || null);
        setRelated(res.data?.related || []);
      })
      .catch((e) => {
        if (!active) return;
        setError(e?.response?.status === 404 ? "not-found" : "error");
      })
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [slug]);

  if (loading) {
    return (
      <div className="min-h-screen bg-cream-base text-ink">
        <Navigation />
        <div className="max-w-4xl mx-auto px-6 py-32 text-center text-ink/55">Loading article…</div>
      </div>
    );
  }

  if (error || !post) {
    return (
      <div className="min-h-screen bg-cream-base text-ink">
        <SEO title="Article not found" noindex url={`/blog/${slug}`} />
        <Navigation />
        <div className="max-w-3xl mx-auto px-6 py-32 text-center">
          <h1 className="font-barlow font-black uppercase text-5xl tracking-tight">Article not found</h1>
          <p className="mt-4 text-ink/65">The article you&apos;re looking for has moved or doesn&apos;t exist.</p>
          <Link
            to="/blog"
            className="inline-flex items-center gap-2 mt-8 bg-forest hover:bg-forest-pop text-cream-card font-barlow font-black uppercase tracking-widest text-xs px-5 py-3 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" /> Back to blog
          </Link>
        </div>
      </div>
    );
  }

  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const jsonLd = articleJsonLd({
    origin,
    title: post.meta_title || post.title,
    description: post.meta_description || post.excerpt,
    image: post.cover_image_url,
    slug: post.slug,
    publishedAt: post.published_at,
    updatedAt: post.updated_at,
    author: post.author_name,
    keywords: post.meta_keywords,
  });
  const breadcrumb = breadcrumbJsonLd(origin, [
    { name: "Home", path: "/" },
    { name: "Blog", path: "/blog" },
    { name: post.title, path: `/blog/${post.slug}` },
  ]);

  return (
    <div className="min-h-screen bg-cream-base text-ink">
      <SEO
        title={post.meta_title || post.title}
        description={post.meta_description || post.excerpt}
        keywords={(post.meta_keywords || []).join(", ")}
        url={`/blog/${post.slug}`}
        image={post.cover_image_url}
        type="article"
        publishedAt={post.published_at}
        updatedAt={post.updated_at}
        author={post.author_name}
        jsonLd={[jsonLd, breadcrumb]}
      />
      <Navigation />

      {/* ===== ARTICLE HERO ===== */}
      <article data-testid="blog-article">
        <header className="relative pt-12 md:pt-20 pb-10 border-b border-gray-border overflow-hidden">
          <div aria-hidden className="absolute -top-32 -left-20 w-96 h-96 rounded-full pointer-events-none" style={{ background: `radial-gradient(circle, ${LIME}1A, transparent 70%)` }} />

          <div className="max-w-3xl mx-auto px-6 md:px-10">
            {/* Breadcrumb */}
            <nav className="flex items-center gap-2 text-[10px] uppercase tracking-[0.25em] font-bold text-ink/55 mb-8" aria-label="Breadcrumb">
              <Link to="/" className="hover:text-forest">Home</Link>
              <span>·</span>
              <Link to="/blog" className="hover:text-forest">Blog</Link>
              {post.category && (
                <>
                  <span>·</span>
                  <Link to={`/blog?category=${encodeURIComponent(post.category)}`} className="hover:text-forest">
                    {post.category}
                  </Link>
                </>
              )}
            </nav>

            {/* Category pill */}
            {post.category && (
              <span className="inline-block mb-6 px-3 py-1 text-[10px] uppercase tracking-[0.25em] font-bold bg-forest text-cream-card">
                {post.category}
              </span>
            )}

            {/* Title */}
            <h1
              data-testid="blog-article-title"
              className="font-barlow font-black uppercase text-4xl md:text-6xl text-ink tracking-tight leading-[0.95]"
            >
              {post.title}
            </h1>
            {post.subtitle && (
              <p className="mt-5 text-xl md:text-2xl text-ink/70 font-serif italic leading-relaxed">
                {post.subtitle}
              </p>
            )}

            {/* Meta row */}
            <div className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-2 text-[11px] uppercase tracking-[0.18em] font-bold text-ink/55">
              <span className="flex items-center gap-1.5">
                <Calendar className="w-3 h-3" /> {formatDate(post.published_at)}
              </span>
              <span className="flex items-center gap-1.5">
                <Clock className="w-3 h-3" /> {post.reading_time_minutes || 5} min read
              </span>
              {post.author_name && (
                <span className="text-ink/70">By {post.author_name}</span>
              )}
            </div>

            <div className="mt-6">
              <BlogShareBar title={post.title} />
            </div>
          </div>
        </header>

        {/* ===== Cover image ===== */}
        {post.cover_image_url && (
          <div className="max-w-5xl mx-auto px-6 md:px-10 -mt-2">
            <img
              src={post.cover_image_url}
              alt={post.cover_image_alt || post.title}
              className="w-full max-h-[520px] object-cover bg-cream-soft mt-10"
              loading="eager"
            />
          </div>
        )}

        {/* ===== Body ===== */}
        <div className="max-w-3xl mx-auto px-6 md:px-10 py-14 md:py-20">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="prose prose-lg prose-stone max-w-none
              prose-headings:font-barlow prose-headings:font-black prose-headings:uppercase prose-headings:tracking-tight
              prose-h2:text-3xl prose-h2:mt-12 prose-h2:mb-5 prose-h2:text-ink
              prose-h3:text-xl prose-h3:mt-8 prose-h3:mb-3 prose-h3:text-ink
              prose-p:text-ink/85 prose-p:leading-relaxed
              prose-a:text-forest prose-a:font-semibold prose-a:no-underline hover:prose-a:underline
              prose-strong:text-ink prose-strong:font-bold
              prose-blockquote:border-l-4 prose-blockquote:border-forest prose-blockquote:bg-forest/5 prose-blockquote:py-2 prose-blockquote:px-5 prose-blockquote:not-italic prose-blockquote:text-ink/80
              prose-ul:my-5 prose-ul:list-disc prose-ul:marker:text-forest
              prose-ol:my-5 prose-ol:marker:text-forest prose-ol:marker:font-bold
              prose-code:bg-cream-soft prose-code:text-forest prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded-none prose-code:before:content-none prose-code:after:content-none
              prose-img:my-8"
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {post.content_md || ""}
            </ReactMarkdown>
          </motion.div>

          {/* Tags */}
          {post.tags && post.tags.length > 0 && (
            <div className="mt-12 pt-8 border-t border-gray-border flex flex-wrap items-center gap-2">
              <TagIcon className="w-3.5 h-3.5 text-ink/50" />
              {post.tags.map((t) => (
                <Link
                  key={t}
                  to={`/blog?tag=${encodeURIComponent(t)}`}
                  className="px-2.5 py-1 text-[10px] uppercase tracking-[0.2em] font-bold border border-gray-border text-ink/60 hover:border-forest hover:text-forest transition-colors"
                >
                  #{t}
                </Link>
              ))}
            </div>
          )}

          {/* Share + back to blog */}
          <div className="mt-12 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-5 border-t border-gray-border pt-8">
            <Link
              to="/blog"
              data-testid="blog-back-link"
              className="inline-flex items-center gap-2 text-[11px] uppercase tracking-[0.22em] font-bold text-ink/60 hover:text-forest transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5" /> All articles
            </Link>
            <BlogShareBar title={post.title} label="Enjoyed it? Share it" />
          </div>

          {/* Newsletter */}
          <div className="mt-10">
            <NewsletterSignup source="article" />
          </div>
        </div>
      </article>

      {/* ===== Related posts ===== */}
      {related.length > 0 && (
        <section className="border-t border-gray-border bg-cream-soft py-14 md:py-20">
          <div className="max-w-6xl mx-auto px-6 md:px-10">
            <h2 className="font-barlow font-black uppercase text-3xl md:text-4xl text-ink tracking-tight mb-10">
              Keep reading
            </h2>
            <div className="grid md:grid-cols-3 gap-5 md:gap-6">
              {related.map((r) => (
                <Link
                  key={r.id}
                  to={`/blog/${r.slug}`}
                  className="group block bg-surface border border-gray-border hover:border-forest-pop transition-all overflow-hidden hover:-translate-y-1 duration-300"
                >
                  {r.cover_image_url && (
                    <div className="aspect-[16/9] overflow-hidden bg-cream-soft">
                      <img src={r.cover_image_url} alt={r.cover_image_alt || r.title} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" loading="lazy" />
                    </div>
                  )}
                  <div className="p-5">
                    <h3 className="font-barlow font-black uppercase text-base text-ink leading-tight group-hover:text-forest transition-colors">
                      {r.title}
                    </h3>
                    <div className="mt-3 text-[10px] uppercase tracking-[0.18em] font-bold text-ink/50 flex items-center gap-3">
                      <Clock className="w-3 h-3" /> {r.reading_time_minutes || 5} min
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* ===== CTA ===== */}
      <section className="border-t border-gray-border bg-forest text-cream-card py-16 md:py-20">
        <div className="max-w-3xl mx-auto px-6 md:px-10 text-center">
          <h2 className="font-barlow font-black uppercase text-3xl md:text-5xl tracking-tight leading-[0.95]">
            Ready to see your game
            <span className="block mt-2" style={{ color: LIME }}>like never before?</span>
          </h2>
          <Link
            to="/signup"
            className="inline-flex items-center gap-2 mt-7 font-barlow font-black uppercase tracking-widest text-sm px-7 py-3.5 rounded-full"
            style={{ background: LIME, color: "#0A1F0F" }}
          >
            Try it free <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </section>
    </div>
  );
}
