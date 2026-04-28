import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { listBlogPosts } from "../api";
import type { BlogPostSummary } from "../types";

function fmtDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function BlogList() {
  const [posts, setPosts] = useState<BlogPostSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    listBlogPosts()
      .then((rows) => alive && setPosts(rows))
      .catch(() => alive && setError("Could not load posts."));
    return () => {
      alive = false;
    };
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!posts) return <p className="muted">Loading…</p>;

  return (
    <>
      <h1>Blog</h1>
      {posts.length === 0 ? (
        <p className="muted">No posts yet.</p>
      ) : (
        <ul className="blog-list">
          {posts.map((p) => (
            <li key={p.slug} className="blog-list__item">
              <h2>
                <Link to={`/blog/${p.slug}`}>{p.title}</Link>
              </h2>
              {p.published_at ? (
                <p className="blog-list__date muted">
                  <time dateTime={p.published_at}>{fmtDate(p.published_at)}</time>
                </p>
              ) : null}
              {p.excerpt ? <p>{p.excerpt}</p> : null}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
