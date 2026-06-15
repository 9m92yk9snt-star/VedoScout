import React from "react";
import { Helmet } from "react-helmet-async";

/**
 * <SEO />  — reusable head tag manager.
 *
 * Props
 * ─────
 * title          string  page <title>
 * description    string  meta description (≤160 chars)
 * keywords       string  comma separated
 * image          string  absolute or relative URL for OG/Twitter card
 * url            string  canonical URL (relative ok — resolved against window.origin)
 * type           string  og:type — "website" | "article" | "profile"
 * jsonLd         object  arbitrary JSON-LD schema object (Article, Organization, …)
 * noindex        bool    add <meta name="robots" content="noindex">
 * publishedAt    string  ISO date (articles)
 * updatedAt      string  ISO date (articles)
 * author         string  article author
 */
export default function SEO({
  title,
  description,
  keywords,
  image,
  url,
  type = "website",
  jsonLd,
  noindex = false,
  publishedAt,
  updatedAt,
  author,
}) {
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const fullUrl = url
    ? (url.startsWith("http") ? url : `${origin}${url.startsWith("/") ? "" : "/"}${url}`)
    : (typeof window !== "undefined" ? window.location.href : "");
  const ogImage = image
    ? (image.startsWith("http") ? image : `${origin}${image.startsWith("/") ? "" : "/"}${image}`)
    : `${origin}/og-default.jpg`;
  const fullTitle = title ? `${title} · ScoutMePlay` : "ScoutMePlay — Where Talent Gets Noticed";
  const desc = description || "Upload your football video and receive a detailed scouting report powered by football intelligence, professional player benchmarks and real scouts. Built for ambitious U7–U21 players.";

  return (
    <Helmet>
      <title>{fullTitle}</title>
      <meta name="description" content={desc} />
      {keywords && <meta name="keywords" content={keywords} />}
      {noindex && <meta name="robots" content="noindex,nofollow" />}
      <link rel="canonical" href={fullUrl} />

      {/* Open Graph */}
      <meta property="og:title" content={fullTitle} />
      <meta property="og:description" content={desc} />
      <meta property="og:url" content={fullUrl} />
      <meta property="og:type" content={type} />
      <meta property="og:image" content={ogImage} />
      <meta property="og:site_name" content="ScoutMePlay" />

      {/* Twitter */}
      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={fullTitle} />
      <meta name="twitter:description" content={desc} />
      <meta name="twitter:image" content={ogImage} />

      {/* Article-specific */}
      {type === "article" && publishedAt && <meta property="article:published_time" content={publishedAt} />}
      {type === "article" && updatedAt && <meta property="article:modified_time" content={updatedAt} />}
      {type === "article" && author && <meta property="article:author" content={author} />}

      {/* JSON-LD structured data */}
      {jsonLd && (
        <script type="application/ld+json">
          {JSON.stringify(jsonLd)}
        </script>
      )}
    </Helmet>
  );
}

/* ── Common JSON-LD builders ─────────────────────────────────────────── */

export const organizationJsonLd = (origin) => ({
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "ScoutMePlay",
  url: origin,
  logo: `${origin}/logo512.png`,
  description: "Premium football video analysis & scouting platform for U7–U21 players.",
  sameAs: [],
});

export const articleJsonLd = ({
  origin,
  title,
  description,
  image,
  slug,
  publishedAt,
  updatedAt,
  author,
  keywords,
}) => ({
  "@context": "https://schema.org",
  "@type": "Article",
  headline: title,
  description,
  image: image ? [image.startsWith("http") ? image : `${origin}${image}`] : [],
  datePublished: publishedAt,
  dateModified: updatedAt || publishedAt,
  author: { "@type": "Organization", name: author || "ScoutMePlay" },
  publisher: {
    "@type": "Organization",
    name: "ScoutMePlay",
    logo: { "@type": "ImageObject", url: `${origin}/logo512.png` },
  },
  mainEntityOfPage: {
    "@type": "WebPage",
    "@id": `${origin}/blog/${slug}`,
  },
  keywords: keywords?.join(", "),
});

export const breadcrumbJsonLd = (origin, items) => ({
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  itemListElement: items.map((it, i) => ({
    "@type": "ListItem",
    position: i + 1,
    name: it.name,
    item: `${origin}${it.path}`,
  })),
});
