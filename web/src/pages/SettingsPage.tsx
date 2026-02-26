import ApiKeySetup from "../components/ApiKeySetup";
import { useNavigate } from "react-router-dom";

export default function SettingsPage() {
  const navigate = useNavigate();

  return (
    <div>
      <h2>Settings</h2>
      <ApiKeySetup onComplete={() => navigate("/")} forceShow />
    </div>
  );
}
