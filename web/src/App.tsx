import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import ProjectListPage from "./pages/ProjectListPage";
import { UnifiedProjectPage } from "./pages/UnifiedProjectPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<ProjectListPage />} />
        <Route path="/create" element={<Navigate to="/project/new" replace />} />
        <Route path="/project/:projectId" element={<UnifiedProjectPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}
