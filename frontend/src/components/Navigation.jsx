import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/lib/auth-context";
import { LogOut, Shield, LayoutDashboard, Upload } from "lucide-react";

export default function Navigation({ transparent = false }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/");
  };

  return (
    <header
      data-testid="main-nav"
      className={`fixed top-0 left-0 right-0 z-50 ${
        transparent ? "bg-deepnavy/40 backdrop-blur-xl" : "bg-deepnavy/90 backdrop-blur-xl"
      } border-b border-white/10`}
    >
      <div className="max-w-7xl mx-auto px-6 md:px-10 py-4 flex items-center justify-between">
        <Link to="/" data-testid="nav-logo" className="flex items-center gap-3 group">
          <div className="w-8 h-8 bg-volt flex items-center justify-center">
            <span className="text-deepnavy font-barlow font-black text-lg leading-none">E</span>
          </div>
          <div className="flex flex-col leading-none">
            <span className="font-barlow font-black uppercase text-white tracking-tight text-lg">Elite Scout</span>
            <span className="text-[10px] text-volt font-bold uppercase tracking-[0.25em]">AI Player Analysis</span>
          </div>
        </Link>

        <nav className="hidden md:flex items-center gap-8">
          {!user && (
            <>
              <Link to="/login" data-testid="nav-link-login" className="text-sm text-white/70 hover:text-volt uppercase tracking-widest font-semibold transition-colors">Sign in</Link>
              <Link to="/signup" data-testid="nav-link-signup" className="text-sm text-white/70 hover:text-volt uppercase tracking-widest font-semibold transition-colors">Sign up</Link>
            </>
          )}
        </nav>

        <div className="flex items-center gap-3">
          {user ? (
            <>
              <Link
                to="/dashboard"
                data-testid="nav-dashboard-btn"
                className="hidden sm:flex items-center gap-2 text-sm text-white/80 hover:text-white uppercase tracking-widest font-semibold transition-colors"
              >
                <LayoutDashboard className="w-4 h-4" />
                Dashboard
              </Link>
              {user.role === "admin" && (
                <Link
                  to="/admin"
                  data-testid="nav-admin-btn"
                  className="hidden sm:flex items-center gap-2 text-sm text-volt hover:text-white uppercase tracking-widest font-semibold transition-colors"
                >
                  <Shield className="w-4 h-4" />
                  Admin
                </Link>
              )}
              <Link
                to="/upload"
                data-testid="nav-upload-cta"
                className="bg-volt hover:bg-white text-deepnavy font-barlow font-black uppercase tracking-widest text-sm px-4 py-2 transition-colors flex items-center gap-2"
              >
                <Upload className="w-4 h-4" />
                Upload
              </Link>
              <button
                onClick={handleLogout}
                data-testid="nav-logout-btn"
                aria-label="Sign out"
                className="text-white/60 hover:text-white p-2 transition-colors"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </>
          ) : (
            <>
              <Link
                to="/login"
                data-testid="nav-login-btn"
                className="text-sm text-white/80 hover:text-white uppercase tracking-widest font-semibold transition-colors"
              >
                Log in
              </Link>
              <Link
                to="/signup"
                data-testid="nav-signup-btn"
                className="bg-volt hover:bg-white text-deepnavy font-barlow font-black uppercase tracking-widest text-sm px-5 py-2.5 transition-colors"
              >
                Get started
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
