import React from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, Send } from "lucide-react";
import Navigation from "@/components/Navigation";

export default function TermsPage() {
  const lastUpdated = "February 2026";

  return (
    <div className="min-h-screen bg-deepnavy text-ink">
      <Navigation />

      <div className="max-w-3xl mx-auto px-6 md:px-10 py-14 md:py-20">
        <Link
          to="/"
          data-testid="terms-back-link"
          className="inline-flex items-center gap-1.5 text-xs uppercase tracking-[0.22em] font-bold text-ink/60 hover:text-forest transition-colors"
        >
          <ChevronLeft className="w-3.5 h-3.5" />
          Back to home
        </Link>

        <h1
          data-testid="terms-page-title"
          className="mt-6 font-barlow font-black uppercase tracking-tighter leading-[0.95] text-4xl sm:text-5xl"
        >
          Terms of Service
        </h1>
        <p className="mt-2 text-sm text-ink/60">
          <span className="uppercase tracking-widest">Servicevilkår</span> · Last updated: {lastUpdated}
        </p>

        <article className="mt-10 space-y-7 text-ink/75 leading-relaxed text-[15px]">
          <Section title="1. Acceptance of these terms">
            <p>
              By creating an account or purchasing a report on ScoutMePlay, you agree to be bound by these Terms of
              Service. If you do not agree, please do not use the service.
            </p>
          </Section>

          <Section title="2. What ScoutMePlay provides">
            <ul className="list-disc list-outside ml-5 space-y-1.5">
              <li>A football video analysis platform that produces a written scouting report based on the video you upload.</li>
              <li>A free preview of the analysis for every new player account.</li>
              <li>A premium report (single or 12-month plan) for a one-time fee, including a personal written review from a real scout or agent.</li>
              <li>A secure dashboard to access your reports and a downloadable PDF version.</li>
            </ul>
          </Section>

          <Section title="3. What ScoutMePlay does NOT promise">
            <p>
              ScoutMePlay provides honest, professional feedback to help young players grow. We{" "}
              <span className="text-ink font-bold">do not</span> promise or guarantee:
            </p>
            <ul className="list-disc list-outside ml-5 space-y-1.5">
              <li>A trial with a club or academy.</li>
              <li>A professional contract.</li>
              <li>A specific score, ranking, or tier — every report reflects the video that was uploaded.</li>
              <li>That a club, scout or agent will contact the player.</li>
            </ul>
            <p>Your report is a tool to guide training and development — not a decision-maker for any club.</p>
          </Section>

          <Section title="4. Eligibility and accounts">
            <ul className="list-disc list-outside ml-5 space-y-1.5">
              <li>You must be at least 16 years old to create an account, or have the consent of a parent or legal guardian.</li>
              <li>You are responsible for keeping your password confidential.</li>
              <li>You must provide accurate information (real name, real email, true date of birth for the player being analysed).</li>
              <li>One free preview is available per account, lifetime.</li>
            </ul>
          </Section>

          <Section title="5. Video and content rights">
            <ul className="list-disc list-outside ml-5 space-y-1.5">
              <li>You must own the rights to any video you upload, or have permission from everyone visible in the video.</li>
              <li>For players under 18, the parent or legal guardian must consent to the upload.</li>
              <li>You grant ScoutMePlay a limited licence to process the video for the sole purpose of producing your report. We do not publish, resell or share your video.</li>
              <li>You retain full ownership of your video and your report.</li>
            </ul>
          </Section>

          <Section title="6. Payments, pricing and refunds">
            <ul className="list-disc list-outside ml-5 space-y-1.5">
              <li>Prices are displayed in USD and shown on the pricing section before checkout.</li>
              <li>All payments are processed securely via Stripe. ScoutMePlay never stores your card details.</li>
              <li>Reports are delivered within 48 hours of payment. If we fail to deliver within 48 hours, you are entitled to a full refund — contact us through the message form.</li>
              <li>The 12-month plan includes 3 reports across 365 days; unused reports expire after 12 months and are not refundable.</li>
              <li>All sales are final once the report has been delivered.</li>
            </ul>
          </Section>

          <Section title="7. Acceptable use">
            <p>You agree not to:</p>
            <ul className="list-disc list-outside ml-5 space-y-1.5">
              <li>Upload content that is illegal, offensive, or violates the privacy of others.</li>
              <li>Attempt to reverse-engineer, scrape, or copy the analysis system.</li>
              <li>Resell or redistribute reports, share card images, or PDFs as your own product.</li>
              <li>Use the service to harass, defame, or unfairly judge any player.</li>
            </ul>
            <p>Accounts that violate these rules may be suspended without refund.</p>
          </Section>

          <Section title="8. Intellectual property">
            <p>
              The ScoutMePlay name, logo, reports, share cards, methodology, and all underlying content are the property
              of ScoutMePlay and are protected by copyright. You may share your own report on social media (we encourage it),
              but you may not modify our branding or claim it as your own work.
            </p>
          </Section>

          <Section title="9. Limitation of liability">
            <p>
              ScoutMePlay is provided &ldquo;as is&rdquo;. We are not liable for any indirect or consequential loss arising from the
              use of our reports — including but not limited to missed trials, club rejections, or contract decisions.
              Our total liability for any claim is limited to the amount you paid for the report in question.
            </p>
          </Section>

          <Section title="10. Service availability">
            <p>
              We do our best to keep the service running 24/7, but we make no guarantees of uninterrupted access.
              Planned maintenance will be communicated where possible. We are not liable for short outages.
            </p>
          </Section>

          <Section title="11. Termination">
            <ul className="list-disc list-outside ml-5 space-y-1.5">
              <li>You can delete your account at any time via the dashboard or by contacting us.</li>
              <li>We may suspend or close accounts that breach these Terms, with reasonable notice where possible.</li>
              <li>Account deletion removes your personal data subject to legal retention obligations (see Privacy Policy).</li>
            </ul>
          </Section>

          <Section title="12. Governing law">
            <p>
              These Terms are governed by the laws of Denmark. Any dispute arising out of or in connection with these
              Terms shall be settled by the competent courts of Denmark.
            </p>
          </Section>

          <Section title="13. Changes to these terms">
            <p>
              We may update these Terms from time to time. The &ldquo;Last updated&rdquo; date at the top of this page shows when the
              most recent change was made. Significant changes will be announced inside your account dashboard.
            </p>
          </Section>

          <Section title="14. Contact">
            <p>For any questions about these Terms, please reach out through our message form:</p>
            <Link
              to="/about#contact"
              data-testid="terms-contact-form"
              className="mt-3 inline-flex items-center gap-2 bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-6 py-3 transition-colors"
            >
              <Send className="w-4 h-4" />
              Send us a message
            </Link>
          </Section>
        </article>
      </div>

      <footer className="border-t border-gray-border py-10 mt-10">
        <div className="max-w-7xl mx-auto px-6 md:px-10 text-center text-[10px] uppercase tracking-[0.22em] text-ink/50">
          © {new Date().getFullYear()} ScoutMePlay · All rights reserved
        </div>
      </footer>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <section>
      <h2 className="font-barlow font-black uppercase tracking-tight text-xl text-ink">{title}</h2>
      <div className="mt-3 space-y-3 text-ink/75">{children}</div>
    </section>
  );
}
