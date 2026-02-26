import { useEffect, useState } from "react";
import { api } from "../api/client";

interface Props {
  onComplete: () => void;
}

export default function ApiKeySetup({ onComplete }: Props) {
  const [loading, setLoading] = useState(true);
  const [anthropicKey, setAnthropicKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.getApiKeyStatus().then((status) => {
      if (status.anthropic_configured && status.openai_configured) {
        onComplete();
      } else {
        setLoading(false);
      }
    });
  }, [onComplete]);

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
        <label htmlFor="anthropic-key">Anthropic API Key</label>
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
        <label htmlFor="openai-key">OpenAI API Key</label>
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
