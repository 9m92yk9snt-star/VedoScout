// BlogShareBar — viral share buttons for blog articles (readers share; brand can 1-click share to its own FB page too).
import React, { useState } from "react";
import { Facebook, Linkedin, Link2, Check, Share2 } from "lucide-react";
import { toast } from "sonner";

const XIcon = (props) => (
  <svg viewBox="0 0 24 24" fill="currentColor" {...props}>
    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231 5.451-6.231Z" />
  </svg>
);

const WhatsAppIcon = (props) => (
  <svg viewBox="0 0 24 24" fill="currentColor" {...props}>
    <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z" />
  </svg>
);

const BTN =
  "w-9 h-9 rounded-full flex items-center justify-center border border-gray-border text-ink/60 bg-surface transition-all duration-200 hover:-translate-y-0.5 hover:text-white";

export default function BlogShareBar({ title, label = "Share" }) {
  const [copied, setCopied] = useState(false);
  const url = typeof window !== "undefined" ? window.location.href : "";
  const enc = encodeURIComponent;

  const pop = (href) => window.open(href, "_blank", "noopener,noreferrer,width=640,height=540");

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      window.prompt("Copy this link:", url);
    }
    setCopied(true);
    toast.success("Link copied — share it anywhere");
    setTimeout(() => setCopied(false), 2500);
  };

  const nativeShare = async () => {
    try {
      await navigator.share({ title, url });
    } catch {
      /* user dismissed */
    }
  };

  return (
    <div className="flex items-center gap-2 flex-wrap" data-testid="blog-share-bar">
      <span className="text-[10px] uppercase tracking-[0.25em] font-bold text-ink/50 mr-1">{label}</span>
      <button
        type="button" aria-label="Share on Facebook" data-testid="blog-share-facebook"
        onClick={() => pop(`https://www.facebook.com/sharer/sharer.php?u=${enc(url)}`)}
        className={BTN} onMouseEnter={(e) => (e.currentTarget.style.background = "#1877F2")} onMouseLeave={(e) => (e.currentTarget.style.background = "")}
      >
        <Facebook className="w-4 h-4" />
      </button>
      <button
        type="button" aria-label="Share on X" data-testid="blog-share-x"
        onClick={() => pop(`https://twitter.com/intent/tweet?url=${enc(url)}&text=${enc(title || "")}`)}
        className={BTN} onMouseEnter={(e) => (e.currentTarget.style.background = "#0f1419")} onMouseLeave={(e) => (e.currentTarget.style.background = "")}
      >
        <XIcon className="w-3.5 h-3.5" />
      </button>
      <button
        type="button" aria-label="Share on WhatsApp" data-testid="blog-share-whatsapp"
        onClick={() => pop(`https://wa.me/?text=${enc(`${title || ""} ${url}`)}`)}
        className={BTN} onMouseEnter={(e) => (e.currentTarget.style.background = "#25D366")} onMouseLeave={(e) => (e.currentTarget.style.background = "")}
      >
        <WhatsAppIcon className="w-4 h-4" />
      </button>
      <button
        type="button" aria-label="Share on LinkedIn" data-testid="blog-share-linkedin"
        onClick={() => pop(`https://www.linkedin.com/sharing/share-offsite/?url=${enc(url)}`)}
        className={BTN} onMouseEnter={(e) => (e.currentTarget.style.background = "#0A66C2")} onMouseLeave={(e) => (e.currentTarget.style.background = "")}
      >
        <Linkedin className="w-4 h-4" />
      </button>
      <button
        type="button" aria-label="Copy link" data-testid="blog-share-copy"
        onClick={copy}
        className={`${BTN} hover:bg-forest`}
      >
        {copied ? <Check className="w-4 h-4 text-forest" /> : <Link2 className="w-4 h-4" />}
      </button>
      {typeof navigator !== "undefined" && !!navigator.share && (
        <button
          type="button" aria-label="Share…" data-testid="blog-share-native"
          onClick={nativeShare}
          className={`${BTN} hover:bg-forest`}
        >
          <Share2 className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}
