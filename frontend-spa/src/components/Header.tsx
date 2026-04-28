import { useEffect, useState } from "react";
import { Link, NavLink } from "react-router-dom";

import { getSite } from "../api";

type Theme = "auto" | "light" | "dark";

const NAV: Array<{ to: string; label: string }> = [
  { to: "/", label: "Home" },
  { to: "/projects", label: "Projects" },
  { to: "/blog", label: "Blog" },
  { to: "/contact", label: "Contact" },
  { to: "/resume", label: "Resume" },
];

function readTheme(): Theme {
  const stored = localStorage.getItem("theme");
  return stored === "light" || stored === "dark" ? stored : "auto";
}

function applyTheme(t: Theme): void {
  if (t === "auto") {
    document.documentElement.removeAttribute("data-theme");
    localStorage.removeItem("theme");
  } else {
    document.documentElement.setAttribute("data-theme", t);
    localStorage.setItem("theme", t);
  }
}

function nextTheme(t: Theme): Theme {
  return t === "auto" ? "light" : t === "light" ? "dark" : "auto";
}

export default function Header() {
  const [siteName, setSiteName] = useState<string>("");
  const [theme, setTheme] = useState<Theme>(readTheme);

  useEffect(() => {
    let alive = true;
    getSite()
      .then((s) => {
        if (alive) setSiteName(s.name);
      })
      .catch(() => {
        /* keep blank */
      });
    return () => {
      alive = false;
    };
  }, []);

  function cycleTheme() {
    const t = nextTheme(theme);
    applyTheme(t);
    setTheme(t);
  }

  return (
    <header className="site-header">
      <Link className="brand" to="/">
        {siteName || "…"}
      </Link>
      <nav className="site-nav">
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.to === "/"}>
            {n.label}
          </NavLink>
        ))}
        <button
          type="button"
          className="theme-toggle"
          aria-label="Toggle color theme"
          onClick={cycleTheme}
        >
          Theme: {theme}
        </button>
      </nav>
    </header>
  );
}
