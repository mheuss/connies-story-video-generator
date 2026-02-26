import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import CreatePage from "./pages/CreatePage";
import ProjectPage from "./pages/ProjectPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<CreatePage />} />
        <Route path="/project/:projectId" element={<ProjectPage />} />
      </Route>
    </Routes>
  );
}
