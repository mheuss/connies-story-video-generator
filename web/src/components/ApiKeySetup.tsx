import { useEffect, useState } from "react";
import { api } from "../api/client";

interface Props {
  onComplete: () => void;
  forceShow?: boolean;
}

export default function ApiKeySetup({ onComplete, forceShow }: Props) {
  const [loading, setLoading] = useState(true);
  const [anthropicKey, setAnthropicKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [anthropicConfigured, setAnthropicConfigured] = useState(false);
  const [openaiConfigured, setOpenaiConfigured] = useState(false);

  useEffect(() => {
    api
      .getApiKeyStatus()
      .then((status) => {
        setAnthropicConfigured(status.anthropic_configured);
        setOpenaiConfigured(status.openai_configured);
        if (status.anthropic_configured && status.openai_configured && !forceShow) {
          onComplete();
        } else {
          setLoading(false);
        }
      })
      .catch(() => {
        setError("Failed to check API key status. Is the backend running?");
        setLoading(false);
      });
  }, [onComplete, forceShow]);

  if (loading) return <p>Checking API keys...</p>;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaving(true);

    try {
      await api.setApiKeys({
        anthropic_api_key: anthropicKey || undefined,
        openai_api_key: openaiKey || undefined,
      });
      onComplete();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save keys");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <h2>API Key Setup</h2>
      <p>
        Enter your API keys to get started. These are stored locally and never
        sent anywhere except to the AI providers.
      </p>

      <div style={{ marginBottom: "1rem" }}>
        <label htmlFor="anthropic-key">
          Anthropic API Key{anthropicConfigured && " (configured)"}
        </label>
        <br />
        <input
          id="anthropic-key"
          type="password"
          value={anthropicKey}
          onChange={(e) => setAnthropicKey(e.target.value)}
          placeholder="sk-ant-..."
          style={{ width: "100%", padding: "0.5rem" }}
        />
      </div>

      <div style={{ marginBottom: "1rem" }}>
        <label htmlFor="openai-key">
          OpenAI API Key{openaiConfigured && " (configured)"}
        </label>
        <br />
        <input
          id="openai-key"
          type="password"
          value={openaiKey}
          onChange={(e) => setOpenaiKey(e.target.value)}
          placeholder="sk-..."
          style={{ width: "100%", padding: "0.5rem" }}
        />
      </div>

      {error && <p style={{ color: "red" }}>{error}</p>}

      <button type="submit" disabled={saving || (!anthropicKey && !openaiKey)}>
        {saving ? "Saving..." : "Save Keys"}
      </button>
    </form>
  );
}
