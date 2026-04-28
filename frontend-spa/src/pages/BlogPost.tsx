import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { ApiError, getBlogPost, submitComment } from "../api";
import type { BlogPostDetail } from "../types";

function fmtDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function BlogPost() {
  const { slug = "" } = useParams<{ slug: string }>();
  const [data, setData] = useState<BlogPostDetail | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [body, setBody] = useState("");
  const [hp, setHp] = useState("");
  const [submitState, setSubmitState] =
    useState<"idle" | "submitting" | "thanks">("idle");
  const [formErrors, setFormErrors] = useState<string[]>([]);

  useEffect(() => {
    let alive = true;
    setData(null);
    setNotFound(false);
    setError(null);
    getBlogPost(slug)
      .then((d) => alive && setData(d))
      .catch((e) => {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 404) {
          setNotFound(true);
        } else {
          setError("Could not load post.");
        }
      });
    return () => {
      alive = false;
    };
  }, [slug]);

  if (notFound) return <p>Post not found.</p>;
  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Loading…</p>;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!data) return;
    setSubmitState("submitting");
    setFormErrors([]);
    try {
      await submitComment(slug, {
        csrf: data.comment_form_token,
        url: hp,
        author_name: name,
        author_email: email,
        body,
      });
      setSubmitState("thanks");
      setName("");
      setEmail("");
      setBody("");
    } catch (err) {
      setSubmitState("idle");
      if (err instanceof ApiError && err.status === 422) {
        const detail = (err.body as { detail?: unknown })?.detail;
        if (Array.isArray(detail)) {
          setFormErrors(detail.map(String));
        } else {
          setFormErrors([String(detail ?? "Validation failed.")]);
        }
      } else if (err instanceof ApiError && err.status === 403) {
        setFormErrors(["Session expired. Refresh the page and try again."]);
      } else {
        setFormErrors(["Network error. Try again."]);
      }
    }
  }

  return (
    <>
      <article className="blog-post">
        {!data.published ? (
          <p className="muted">Draft — not visible to the public.</p>
        ) : null}
        <h1>{data.title}</h1>
        {data.published_at ? (
          <p className="blog-post__date muted">
            <time dateTime={data.published_at}>{fmtDate(data.published_at)}</time>
          </p>
        ) : null}
        <div
          className="blog-post__body"
          dangerouslySetInnerHTML={{ __html: data.body_html }}
        />
      </article>

      <section className="comments" aria-label="Comments">
        <h2>Comments</h2>

        {submitState === "thanks" ? (
          <p
            className="thanks-banner"
            style={{
              display: "block",
              padding: "0.6rem 0.85rem",
              borderRadius: 6,
              background: "#ecfeff",
              color: "#0e7490",
              marginBottom: "1rem",
            }}
          >
            Thanks — your comment is awaiting moderation.
          </p>
        ) : null}

        {data.comments.length === 0 ? (
          <p className="muted">No comments yet — be the first.</p>
        ) : (
          <ul className="comment-list">
            {data.comments.map((c, i) => (
              <li key={i} className="comment">
                <p className="comment__meta">
                  <strong>{c.author_name}</strong>
                  {c.created_at ? (
                    <time className="muted" dateTime={c.created_at}>
                      {" "}
                      · {fmtDate(c.created_at)}
                    </time>
                  ) : null}
                </p>
                <p className="comment__body">{c.body}</p>
              </li>
            ))}
          </ul>
        )}

        {formErrors.length > 0 ? (
          <ul className="error">
            {formErrors.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        ) : null}

        <form onSubmit={onSubmit} className="admin-form comment-form">
          <div className="hp" aria-hidden="true">
            <label>
              Leave this field blank
              <input
                type="text"
                name="url"
                value={hp}
                onChange={(e) => setHp(e.target.value)}
                tabIndex={-1}
                autoComplete="off"
              />
            </label>
          </div>
          <label>
            Name
            <input
              name="author_name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              maxLength={80}
            />
          </label>
          <label>
            Email <span className="muted">(not published)</span>
            <input
              name="author_email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              maxLength={120}
            />
          </label>
          <label>
            Comment
            <textarea
              name="body"
              rows={5}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              required
              maxLength={4000}
            />
          </label>
          <button type="submit" disabled={submitState === "submitting"}>
            {submitState === "submitting" ? "Submitting…" : "Post comment"}
          </button>
        </form>
      </section>
    </>
  );
}
