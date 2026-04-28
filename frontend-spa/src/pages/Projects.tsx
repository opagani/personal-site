import { useEffect, useState } from "react";

import { getProjects } from "../api";
import type { Project } from "../types";

export default function Projects() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getProjects()
      .then((rows) => alive && setProjects(rows))
      .catch(() => alive && setError("Could not load projects."));
    return () => {
      alive = false;
    };
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!projects) return <p className="muted">Loading…</p>;

  return (
    <>
      <h1>Projects</h1>
      <ul className="project-list">
        {projects.map((p) => (
          <li key={p.id} className="project-card">
            <h2>{p.link ? <a href={p.link}>{p.title}</a> : p.title}</h2>
            <p>{p.description}</p>
          </li>
        ))}
      </ul>
    </>
  );
}
