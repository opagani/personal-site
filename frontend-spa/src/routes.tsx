import { createBrowserRouter } from "react-router-dom";

import App from "./App";
import BlogList from "./pages/BlogList";
import BlogPost from "./pages/BlogPost";
import Contact from "./pages/Contact";
import Home from "./pages/Home";
import NotFound from "./pages/NotFound";
import Projects from "./pages/Projects";
import Resume from "./pages/Resume";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Home /> },
      { path: "projects", element: <Projects /> },
      { path: "blog", element: <BlogList /> },
      { path: "blog/:slug", element: <BlogPost /> },
      { path: "contact", element: <Contact /> },
      { path: "resume", element: <Resume /> },
      { path: "*", element: <NotFound /> },
    ],
  },
]);
