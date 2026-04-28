import { Outlet } from "react-router-dom";

export default function App() {
  return (
    <>
      <main className="site-main">
        <Outlet />
      </main>
    </>
  );
}
