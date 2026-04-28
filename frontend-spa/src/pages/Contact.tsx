import { useEffect, useState } from "react";

import { getLinks } from "../api";
import type { LinkItem } from "../types";

export default function Contact() {
  const [links, setLinks] = useState<LinkItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getLinks()
      .then((rows) => alive && setLinks(rows))
      .catch(() => alive && setError("Could not load contact links."));
    return () => {
      alive = false;
    };
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!links) return <p className="muted">Loading…</p>;

  return (
    <>
      <h1>Contact</h1>
      <p>Easiest ways to reach me:</p>
      <ul className="link-list">
        {links.map((l) => (
          <li key={l.id}>
            <a href={l.url}>{l.label}</a>
          </li>
        ))}
      </ul>
    </>
  );
}
