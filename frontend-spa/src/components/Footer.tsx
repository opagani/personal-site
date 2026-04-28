import { useEffect, useState } from "react";

import { getSite } from "../api";

export default function Footer() {
  const [siteName, setSiteName] = useState<string>("");

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

  return (
    <footer className="site-footer">
      <small>&copy; {siteName || ""}</small>
      <small className="site-footer__owner">
        <a href="/admin/login">Site owner? Sign in to edit</a>
      </small>
    </footer>
  );
}
