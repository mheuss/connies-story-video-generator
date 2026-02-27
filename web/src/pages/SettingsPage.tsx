import { Link } from "react-router-dom";
import ApiKeySetup from "../components/ApiKeySetup";
import { useNavigate } from "react-router-dom";

export default function SettingsPage() {
  const navigate = useNavigate();

  return (
    <div>
      <h2>Settings</h2>
      <p><Link to="/">Back to home</Link></p>
      <ApiKeySetup onComplete={() => navigate("/")} forceShow />
    </div>
  );
}
