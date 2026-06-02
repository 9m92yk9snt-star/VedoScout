import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth-context";
import Navigation from "@/components/Navigation";
import { ArrowRight } from "lucide-react";

export default function Signup() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { signup } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (password.length < 6) {
      toast.error("Password must be at least 6 characters");
      return;
    }
    setSubmitting(true);
    try {
      await signup(email, password, fullName);
      toast.success("Account created. Let's upload your video.");
      navigate("/upload");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Sign up failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-deepnavy text-white">
      <Navigation />
      <div className="pt-32 pb-20 px-6">
        <div className="max-w-md mx-auto">
          <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">Get started</span>
          <h1 className="mt-3 font-barlow font-black uppercase text-5xl tracking-tighter leading-[0.95]">Create account</h1>
          <p className="mt-3 text-white/60 text-sm">Free preview included. No card required to start.</p>

          <form onSubmit={handleSubmit} className="mt-10 space-y-5" data-testid="signup-form">
            <div>
              <label className="text-xs uppercase tracking-[0.2em] font-bold text-white/50 block mb-2">Full name</label>
              <input
                type="text"
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                data-testid="signup-name"
                className="w-full bg-surface border border-white/10 px-4 py-3 text-white focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt transition-colors"
                placeholder="Jane Doe"
              />
            </div>
            <div>
              <label className="text-xs uppercase tracking-[0.2em] font-bold text-white/50 block mb-2">Email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                data-testid="signup-email"
                className="w-full bg-surface border border-white/10 px-4 py-3 text-white focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt transition-colors"
                placeholder="you@email.com"
              />
            </div>
            <div>
              <label className="text-xs uppercase tracking-[0.2em] font-bold text-white/50 block mb-2">Password</label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                data-testid="signup-password"
                className="w-full bg-surface border border-white/10 px-4 py-3 text-white focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt transition-colors"
                placeholder="At least 6 characters"
              />
            </div>
            <button
              type="submit"
              disabled={submitting}
              data-testid="signup-submit"
              className="w-full bg-volt hover:bg-white text-deepnavy font-barlow font-black uppercase tracking-widest text-base px-8 py-4 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {submitting ? "Creating..." : "Create account"}
              {!submitting && <ArrowRight className="w-4 h-4" />}
            </button>
          </form>

          <p className="mt-8 text-sm text-white/50 text-center">
            Have an account?{" "}
            <Link to="/login" data-testid="signup-to-login" className="text-volt hover:text-white transition-colors uppercase tracking-widest font-semibold">
              Log in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
