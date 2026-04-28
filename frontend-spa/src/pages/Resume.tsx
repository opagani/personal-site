import { useEffect, useState } from "react";

import { getResume } from "../api";
import type { ResumeData } from "../types";

export default function Resume() {
  const [data, setData] = useState<ResumeData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getResume()
      .then((d) => alive && setData(d))
      .catch(() => alive && setError("Could not load resume."));
    return () => {
      alive = false;
    };
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Loading…</p>;

  return (
    <>
      <h1>Resume</h1>
      <div
        className="resume-body"
        dangerouslySetInnerHTML={{ __html: data.summary_html }}
      />
      {data.pdf_available && data.pdf_path ? (
        <p>
          <a className="button" href={data.pdf_path} download>
            Download PDF
          </a>
        </p>
      ) : (
        <p className="muted">
          PDF not yet uploaded. Drop one at <code>frontend/static/resume.pdf</code>{" "}
          to enable the download link.
        </p>
      )}
    </>
  );
}
