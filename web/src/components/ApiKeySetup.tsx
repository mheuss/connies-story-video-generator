import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";

interface Props {
  onComplete: () => void;
  forceShow?: boolean;
}

export default function ApiKeySetup({ onComplete, forceShow }: Props) {
  const [loading, setLoading] = useState(true);
  const [anthropicKey, setAnthropicKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [elevenlabsKey, setElevenlabsKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [anthropicConfigured, setAnthropicConfigured] = useState(false);
  const [openaiConfigured, setOpenaiConfigured] = useState(false);
  const [elevenlabsConfigured, setElevenlabsConfigured] = useState(false);
  const hasRequiredKeys =
    (anthropicConfigured || anthropicKey.trim() !== "") &&
    (openaiConfigured || openaiKey.trim() !== "");

  useEffect(() => {
    api
      .getApiKeyStatus()
      .then((status) => {
        setAnthropicConfigured(status.anthropic_configured);
        setOpenaiConfigured(status.openai_configured);
        setElevenlabsConfigured(status.elevenlabs_configured);
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
        anthropic_api_key: anthropicKey.trim() || undefined,
        openai_api_key: openaiKey.trim() || undefined,
        elevenlabs_api_key: elevenlabsKey.trim() || undefined,
      });
      onComplete();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save keys");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>API Key Setup</CardTitle>
        <CardDescription>
          Enter your API keys to get started. These are stored locally and never
          sent anywhere except to the AI providers.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="anthropic-key" className="block text-sm font-medium text-foreground">
              Anthropic API Key{anthropicConfigured && " (configured)"}
            </label>
            <input
              id="anthropic-key"
              type="password"
              value={anthropicKey}
              onChange={(e) => setAnthropicKey(e.target.value)}
              placeholder="sk-ant-..."
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="openai-key" className="block text-sm font-medium text-foreground">
              OpenAI API Key{openaiConfigured && " (configured)"}
            </label>
            <input
              id="openai-key"
              type="password"
              value={openaiKey}
              onChange={(e) => setOpenaiKey(e.target.value)}
              placeholder="sk-..."
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="elevenlabs-key" className="block text-sm font-medium text-foreground">
              ElevenLabs API Key (optional){elevenlabsConfigured && " (configured)"}
            </label>
            <input
              id="elevenlabs-key"
              type="password"
              value={elevenlabsKey}
              onChange={(e) => setElevenlabsKey(e.target.value)}
              placeholder="sk_..."
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>

          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}

          <Button
            type="submit"
            disabled={saving || !hasRequiredKeys}
          >
            {saving ? "Saving..." : "Save Keys"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
