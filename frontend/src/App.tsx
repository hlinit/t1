import { useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

function App() {
  const [t4File, setT4File] = useState<File | null>(null);
  const [error, setError] = useState<string>("");
  const [status, setStatus] = useState<string>("");
  const [notification, setNotification] = useState<string>("");
  const [isProcessing, setIsProcessing] = useState<boolean>(false);

  const resetMessages = () => {
    setError("");
    setStatus("");
    setNotification("");
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    resetMessages();
    const file = event.target.files?.[0] ?? null;
    setT4File(file);
  };

  const handleProcess = async () => {
    if (!t4File) {
      setError("Please choose a T4 PDF before processing.");
      return;
    }

    setError("");
    setNotification("");
    setStatus("Uploading T4 slip…");
    setIsProcessing(true);

    try {
      const form = new FormData();
      form.append("file", t4File);

      const response = await fetch(`${API_BASE}/api/process`, {
        method: "POST",
        body: form,
      });

      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail?.error ?? response.statusText);
      }

      setStatus("Generating your completed T1…");

      if (response.headers.get("content-type")?.includes("application/json")) {
        const json = await response.json();
        if (json?.url) {
          window.open(json.url, "_blank");
          setNotification("Your completed T1 has been generated. It opened in a new tab.");
          setStatus("");
          return;
        }
      }

      setStatus("Preparing download…");
      const blob = await response.blob();
      const downloadUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = downloadUrl;
      link.download = "Completed-T1.pdf";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(downloadUrl);
      setNotification("Your completed T1 has been downloaded.");
      setStatus("");
    } catch (err) {
      setStatus("");
      setError(err instanceof Error ? err.message : "Processing failed");
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <main
      style={{
        fontFamily: "Inter, system-ui, sans-serif",
        maxWidth: 720,
        margin: "0 auto",
        padding: "3rem 1.5rem",
      }}
    >
      <header style={{ marginBottom: "2.5rem" }}>
        <h1 style={{ fontSize: "2.5rem", marginBottom: "0.5rem" }}>AI T1 Filing Assistant</h1>
        <p style={{ color: "#555", margin: 0 }}>
          Upload a T4 slip and we will automatically produce a filled CRA T1 return.
        </p>
      </header>

      <section
        style={{
          background: "#f7f8fa",
          borderRadius: "12px",
          padding: "2rem",
          boxShadow: "0 1px 3px rgba(15, 23, 42, 0.08)",
        }}
      >
        <h2 style={{ fontSize: "1.5rem", marginBottom: "1rem" }}>Process T4 → T1</h2>
        <p style={{ color: "#444", marginBottom: "1.5rem" }}>
          Select a T4 PDF file, then click <strong>Process T4</strong>. We will extract the data,
          map it to the correct CRA lines, fill the T1 form, and download the completed return.
        </p>

        <div style={{ display: "flex", gap: "1rem", alignItems: "center", marginBottom: "1.5rem" }}>
          <input
            type="file"
            accept="application/pdf"
            onChange={handleFileChange}
            disabled={isProcessing}
          />
          <button
            onClick={handleProcess}
            disabled={isProcessing}
            style={{
              backgroundColor: isProcessing ? "#cbd5f5" : "#3b82f6",
              color: "white",
              border: "none",
              borderRadius: "999px",
              padding: "0.75rem 1.75rem",
              fontSize: "1rem",
              cursor: isProcessing ? "not-allowed" : "pointer",
              transition: "background-color 0.2s ease",
            }}
          >
            {isProcessing ? "Processing…" : "Process T4"}
          </button>
        </div>

        {status && (
          <div
            style={{
              background: "#e0f2fe",
              color: "#0369a1",
              padding: "0.75rem 1rem",
              borderRadius: "8px",
              marginBottom: "1rem",
            }}
          >
            {status}
          </div>
        )}

        {notification && (
          <div
            style={{
              background: "#dcfce7",
              color: "#166534",
              padding: "0.75rem 1rem",
              borderRadius: "8px",
              marginBottom: "1rem",
            }}
          >
            {notification}
          </div>
        )}

        {error && (
          <div
            style={{
              background: "#fee2e2",
              color: "#b91c1c",
              padding: "0.75rem 1rem",
              borderRadius: "8px",
            }}
          >
            {error}
          </div>
        )}
      </section>
    </main>
  );
}

export default App;
