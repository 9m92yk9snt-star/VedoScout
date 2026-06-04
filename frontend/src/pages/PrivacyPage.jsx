import React from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, Mail } from "lucide-react";
import Navigation from "@/components/Navigation";

export default function PrivacyPage() {
  const lastUpdated = "June 2026";

  return (
    <div className="min-h-screen bg-deepnavy text-ink">
      <Navigation />

      <div className="max-w-3xl mx-auto px-6 md:px-10 py-14 md:py-20">
        <Link
          to="/"
          data-testid="privacy-back-link"
          className="inline-flex items-center gap-1.5 text-xs uppercase tracking-[0.22em] font-bold text-ink/60 hover:text-volt transition-colors"
        >
          <ChevronLeft className="w-3.5 h-3.5" />
          Back to home
        </Link>

        <h1 className="mt-6 font-barlow font-black uppercase tracking-tighter leading-[0.95] text-4xl sm:text-5xl">
          Privacy Policy
        </h1>
        <p className="mt-2 text-sm text-ink/60">
          <span className="uppercase tracking-widest">Privatlivspolitik</span> · Last updated: {lastUpdated}
        </p>

        <article className="mt-10 space-y-7 text-ink/75 leading-relaxed text-[15px]">
          <Section title="1. Who we are">
            <p>
              ScoutMePlay is operated by <span className="text-volt font-bold">Mentalkids</span>, based in Denmark.
              For all questions about this Privacy Policy or how we handle your personal data, please contact us
              at <a className="text-volt underline" href="mailto:scoutmeplay@gmail.com">scoutmeplay@gmail.com</a>.
            </p>
          </Section>

          <Section title="2. What personal data we collect">
            <ul className="list-disc list-outside ml-5 space-y-1.5">
              <li><span className="text-ink">Account data</span> — your full name, email address and password (stored hashed; we never see your plain-text password).</li>
              <li><span className="text-ink">Video data</span> — the football videos you upload, the screenshot of the moment you marked your player, and metadata such as the player's age and position.</li>
              <li><span className="text-ink">Payment data</span> — when you pay, Stripe processes your card details on their secure servers. We only see the transaction ID, the amount, and a brand/source tag (we never see your full card number).</li>
              <li><span className="text-ink">Usage data</span> — basic technical information such as your IP address, browser and what pages you load. Used to keep the service running and detect abuse.</li>
            </ul>
          </Section>

          <Section title="3. Why we process your data (legal bases under GDPR)">
            <ul className="list-disc list-outside ml-5 space-y-1.5">
              <li><span className="text-ink">Contract performance (GDPR art. 6(1)(b))</span> — to deliver the analysis report you purchased.</li>
              <li><span className="text-ink">Legitimate interest (GDPR art. 6(1)(f))</span> — to improve the AI scoring engine, prevent fraud, and run our scout review queue.</li>
              <li><span className="text-ink">Legal obligation (GDPR art. 6(1)(c))</span> — to retain accounting records for payment transactions (Danish bookkeeping law requires 5 years).</li>
              <li><span className="text-ink">Consent (GDPR art. 6(1)(a))</span> — only for optional marketing emails (if you opt in).</li>
            </ul>
          </Section>

          <Section title="4. Third parties who process your data on our behalf">
            <ul className="list-disc list-outside ml-5 space-y-1.5">
              <li><span className="text-ink">Stripe</span> (payment processor) — processes your card details and stores your transaction history. See <a href="https://stripe.com/privacy" className="text-volt underline">stripe.com/privacy</a>.</li>
              <li><span className="text-ink">Google Gemini</span> (AI provider) — your uploaded video is sent to Google's Gemini API for analysis. Google does not use your video to train their models when accessed via the paid API. See <a href="https://policies.google.com/privacy" className="text-volt underline">policies.google.com/privacy</a>.</li>
              <li><span className="text-ink">Hosting infrastructure</span> — our servers run on European-region data centers.</li>
            </ul>
            <p>
              We have data-processing agreements with each of these providers as required by GDPR.
              Some processing may take place outside the EU/EEA (notably with Google) — we rely on the
              EU Standard Contractual Clauses for those transfers.
            </p>
          </Section>

          <Section title="5. How long we keep your data">
            <ul className="list-disc list-outside ml-5 space-y-1.5">
              <li>Reports and uploaded videos: kept while your account is active, or up to <span className="text-ink">12 months after your last login</span>.</li>
              <li>Payment transaction records: <span className="text-ink">5 years</span> (Danish bookkeeping requirement).</li>
              <li>Account data: deleted when you ask us to delete your account.</li>
            </ul>
          </Section>

          <Section title="6. Your rights under GDPR">
            <p>You have the right to:</p>
            <ul className="list-disc list-outside ml-5 space-y-1.5">
              <li><span className="text-ink">Access</span> — get a copy of the personal data we hold about you.</li>
              <li><span className="text-ink">Rectification</span> — correct inaccurate personal data.</li>
              <li><span className="text-ink">Erasure</span> ("right to be forgotten") — request that we delete your account and reports.</li>
              <li><span className="text-ink">Restriction</span> — ask us to pause processing while a dispute is resolved.</li>
              <li><span className="text-ink">Portability</span> — receive your data in a structured machine-readable format.</li>
              <li><span className="text-ink">Objection</span> — object to processing based on legitimate interest.</li>
              <li><span className="text-ink">Withdraw consent</span> — at any time, where consent is the legal basis.</li>
            </ul>
            <p>
              To exercise any of these rights, email <a className="text-volt underline" href="mailto:scoutmeplay@gmail.com">scoutmeplay@gmail.com</a> from
              the email address tied to your account. We respond within 30 days.
            </p>
          </Section>

          <Section title="7. Cookies and tracking">
            <p>
              We use only the technical cookies strictly necessary to keep you logged in. We do not run
              third-party advertising cookies, retargeting pixels, or behavioural tracking. If we add
              analytics in the future, we'll update this policy and ask for your consent first.
            </p>
          </Section>

          <Section title="8. Children">
            <p>
              ScoutMePlay is intended for players aged 13 and up — but younger players use the service through
              a parent or guardian account. If you're under 13, please ask a parent to create the account on
              your behalf. If you believe we hold data for a child under 13 without parental consent, email us
              and we'll delete it immediately.
            </p>
          </Section>

          <Section title="9. Security">
            <p>
              Passwords are stored with bcrypt hashing. Payment details never touch our servers — Stripe
              handles all card processing. All connections use HTTPS / TLS 1.2+.
            </p>
          </Section>

          <Section title="10. Right to complain">
            <p>
              If you believe we've handled your data unlawfully, you have the right to complain to the Danish
              Data Protection Agency (<a className="text-volt underline" href="https://www.datatilsynet.dk">Datatilsynet</a>),
              or your local data-protection authority in the EU/EEA.
            </p>
          </Section>

          <Section title="11. Changes to this policy">
            <p>
              We may update this policy from time to time. The "Last updated" date at the top tells you when.
              Material changes will be communicated by email to all active users.
            </p>
          </Section>

          <div className="border-t border-gray-border pt-7 mt-2">
            <p className="text-sm">
              Questions? Reach us anytime:
            </p>
            <a
              href="mailto:scoutmeplay@gmail.com"
              data-testid="privacy-contact-email"
              className="mt-3 inline-flex items-center gap-2 bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-6 py-3 transition-colors"
            >
              <Mail className="w-4 h-4" />
              scoutmeplay@gmail.com
            </a>
          </div>
        </article>
      </div>

      <footer className="border-t border-gray-border py-10 mt-10">
        <div className="max-w-7xl mx-auto px-6 md:px-10 text-center text-[10px] uppercase tracking-[0.22em] text-ink/50">
          © {new Date().getFullYear()} Mentalkids · ScoutMePlay · All rights reserved
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
