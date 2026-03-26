import { useCallback, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

interface FileDropZoneProps {
  accept: string[];
  maxSizeBytes: number;
  onFileRead: (content: string, filename: string) => void;
  onClear: () => void;
  filename?: string;
  error?: string;
  disabled?: boolean;
}

function FileDropZone({
  accept,
  maxSizeBytes,
  onFileRead,
  onClear,
  filename,
  error: externalError,
  disabled = false,
}: FileDropZoneProps) {
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const displayError = externalError || error;

  const validateAndRead = useCallback(
    (file: File) => {
      setError(null);

      const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
      if (!accept.includes(ext)) {
        setError(`Only ${accept.join(" and ")} files are supported`);
        return;
      }

      if (file.size > maxSizeBytes) {
        setError(
          `File too large (max ${Math.round(maxSizeBytes / 1024 / 1024)} MB)`,
        );
        return;
      }

      const reader = new FileReader();
      reader.onload = () => {
        onFileRead(reader.result as string, file.name);
      };
      reader.onerror = () => {
        setError("Could not read file");
      };
      reader.readAsText(file);
    },
    [accept, maxSizeBytes, onFileRead],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      if (disabled) return;
      const file = e.dataTransfer.files[0];
      if (file) validateAndRead(file);
    },
    [disabled, validateAndRead],
  );

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    if (!disabled) setDragOver(true);
  }, [disabled]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    if (!disabled) setDragOver(true);
  }, [disabled]);

  const handleDragLeave = useCallback(() => {
    setDragOver(false);
  }, []);

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) validateAndRead(file);
      // Reset so the same file can be re-selected
      e.target.value = "";
    },
    [validateAndRead],
  );

  if (filename) {
    return (
      <div data-slot="file-drop-zone" className="mb-4">
        <div className="flex items-center gap-3 rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-900">
          <svg
            className="size-5 shrink-0 text-gray-400"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z"
            />
          </svg>
          <span className="flex-1 truncate text-sm">{filename}</span>
          <Button
            variant="ghost"
            size="xs"
            onClick={onClear}
            aria-label="Remove file"
          >
            Remove
          </Button>
        </div>
        {displayError && (
          <p role="alert" className="mt-1 text-sm text-red-600 dark:text-red-400">
            {displayError}
          </p>
        )}
      </div>
    );
  }

  return (
    <div data-slot="file-drop-zone" className="mb-4">
      <div
        onDrop={handleDrop}
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        className={cn(
          "flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-6 transition-colors",
          dragOver
            ? "border-blue-500 bg-blue-50 dark:bg-blue-950"
            : "border-gray-300 dark:border-gray-600",
          disabled && "cursor-not-allowed opacity-50",
        )}
      >
        <svg
          className="size-8 text-gray-400"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5"
          />
        </svg>
        <p className="text-sm text-gray-500">Drop a text file here or</p>
        <Button
          variant="outline"
          size="sm"
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
        >
          Browse files
        </Button>
        <p className="text-xs text-gray-400">
          .txt or .md, up to {Math.round(maxSizeBytes / 1024 / 1024)} MB
        </p>
        <input
          ref={inputRef}
          type="file"
          accept={accept.join(",")}
          onChange={handleInputChange}
          className="hidden"
          aria-hidden="true"
        />
      </div>
      {displayError && (
        <p role="alert" className="mt-1 text-sm text-red-600 dark:text-red-400">
          {displayError}
        </p>
      )}
    </div>
  );
}

export { FileDropZone };
export type { FileDropZoneProps };
