import { Link } from "react-router-dom";
import ApiKeySetup from "../components/ApiKeySetup";
import { useNavigate } from "react-router-dom";

export default function SettingsPage() {
  const navigate = useNavigate();

  return (
    <div>
      <h2 className="text-lg font-semibold mb-2">Settings</h2>
      <p className="mb-6">
        <Link to="/" className="text-sm text-muted-foreground hover:text-foreground">
          Back to home
        </Link>
      </p>
      <ApiKeySetup onComplete={() => navigate("/")} forceShow />
    </div>
  );
}
