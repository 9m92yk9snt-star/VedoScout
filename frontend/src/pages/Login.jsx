import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth-context";
import Navigation from "@/components/Navigation";
import { ArrowRight } from "lucide-react";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const u = await login(email, password);
      toast.success("Welcome back");
      navigate(u.role === "admin" ? "/admin" : "/dashboard");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Login failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-deepnavy text-white">
      <Navigation />
      <div className="pt-32 pb-20 px-6">
        <div className="max-w-md mx-auto">
          <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">Welcome back</span>
          <h1 className="mt-3 font-barlow font-black uppercase text-5xl tracking-tighter leading-[0.95]">Log in</h1>
          <p className="mt-3 text-white/60 text-sm">Access your dashboard and player reports.</p>

          <form onSubmit={handleSubmit} className="mt-10 space-y-5" data-testid="login-form">
            <div>
              <label className="text-xs uppercase tracking-[0.2em] font-bold text-white/50 block mb-2">Email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                data-testid="login-email"
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
                data-testid="login-password"
                className="w-full bg-surface border border-white/10 px-4 py-3 text-white focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt transition-colors"
                placeholder="••••••••"
              />
            </div>
            <button
              type="submit"
              disabled={submitting}
              data-testid="login-submit"
              className="w-full bg-volt hover:bg-white text-deepnavy font-barlow font-black uppercase tracking-widest text-base px-8 py-4 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {submitting ? "Signing in..." : "Log in"}
              {!submitting && <ArrowRight className="w-4 h-4" />}
            </button>
          </form>

          <p className="mt-8 text-sm text-white/50 text-center">
            New here?{" "}
            <Link to="/signup" data-testid="login-to-signup" className="text-volt hover:text-white transition-colors uppercase tracking-widest font-semibold">
              Create account
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
