import type {
  BlogPostDetail,
  BlogPostSummary,
  LinkItem,
  Project,
  ResumeData,
  Site,
  SubmitCommentInput,
} from "./types";

class ApiError extends Error {
  constructor(public status: number, public body: unknown, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(path, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (!r.ok) {
    let body: unknown = null;
    try {
      body = await r.json();
    } catch {
      /* ignore */
    }
    throw new ApiError(r.status, body, `GET ${path} failed: ${r.status}`);
  }
  return (await r.json()) as T;
}

async function postJson<T>(path: string, payload: unknown): Promise<T> {
  const r = await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) {
    let body: unknown = null;
    try {
      body = await r.json();
    } catch {
      /* ignore */
    }
    throw new ApiError(r.status, body, `POST ${path} failed: ${r.status}`);
  }
  return (await r.json()) as T;
}

export { ApiError };

export const getSite = () => getJson<Site>("/api/site");
export const getProjects = () => getJson<Project[]>("/api/projects");
export const getLinks = () => getJson<LinkItem[]>("/api/links");
export const getResume = () => getJson<ResumeData>("/api/resume");
export const listBlogPosts = () => getJson<BlogPostSummary[]>("/api/blog/posts");
export const getBlogPost = (slug: string) =>
  getJson<BlogPostDetail>(`/api/blog/posts/${encodeURIComponent(slug)}`);
export const submitComment = (slug: string, input: SubmitCommentInput) =>
  postJson<{ ok: true }>(
    `/api/blog/posts/${encodeURIComponent(slug)}/comments`,
    input,
  );
