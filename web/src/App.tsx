import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import CreatePage from "./pages/CreatePage";
import ProjectListPage from "./pages/ProjectListPage";
import ProjectPage from "./pages/ProjectPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<ProjectListPage />} />
        <Route path="/create" element={<CreatePage />} />
        <Route path="/project/:projectId" element={<ProjectPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}
