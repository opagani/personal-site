export type Site = {
  name: string;
  headline: string;
  bio: string;
  avatar_url: string | null;
};

export type Project = {
  id: number;
  title: string;
  description: string;
  link: string | null;
  position: number;
};

export type LinkItem = {
  id: number;
  label: string;
  url: string;
  position: number;
};

export type ResumeData = {
  summary_html: string;
  pdf_path: string | null;
  pdf_available: boolean;
};

export type BlogPostSummary = {
  slug: string;
  title: string;
  excerpt: string | null;
  published_at: string | null;
};

export type BlogComment = {
  author_name: string;
  body: string;
  created_at: string | null;
};

export type BlogPostDetail = {
  slug: string;
  title: string;
  published: boolean;
  published_at: string | null;
  body_html: string;
  comment_form_token: string;
  comments: BlogComment[];
};

export type SubmitCommentInput = {
  csrf: string;
  url: string;
  author_name: string;
  author_email: string;
  body: string;
};
