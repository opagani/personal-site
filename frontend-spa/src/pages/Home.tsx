import { useEffect, useState } from "react";

import { getSite } from "../api";
import type { Site } from "../types";

export default function Home() {
  const [site, setSite] = useState<Site | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getSite()
      .then((s) => alive && setSite(s))
      .catch(() => alive && setError("Could not load site info."));
    return () => {
      alive = false;
    };
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!site) return <p className="muted">Loading…</p>;

  return (
    <section className="hero">
      {site.avatar_url ? (
        <img className="avatar" src={site.avatar_url} alt={site.name} />
      ) : null}
      <h1>{site.name}</h1>
      <p className="headline">{site.headline}</p>
      <p className="bio">{site.bio}</p>
    </section>
  );
}
