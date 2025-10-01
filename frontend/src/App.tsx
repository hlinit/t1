import { useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

function App() {
  const [t4File, setT4File] = useState<File | null>(null);
  const [extractResult, setExtractResult] = useState<string>("");
  const [extractError, setExtractError] = useState<string>("");

  const [mapInput, setMapInput] = useState<string>("");
  const [mapResult, setMapResult] = useState<string>("");
  const [mapError, setMapError] = useState<string>("");

  const [fillInput, setFillInput] = useState<string>("");
  const [fillError, setFillError] = useState<string>("");

  const [processFile, setProcessFile] = useState<File | null>(null);
  const [processError, setProcessError] = useState<string>("");

  const handleExtract = async () => {
    if (!t4File) {
      setExtractError("Please choose a T4 PDF first.");
      return;
    }
    setExtractError("");
    try {
      const form = new FormData();
      form.append("file", t4File);
      const response = await fetch(`${API_BASE}/api/extract`, {
        method: "POST",
        body: form,
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail?.error ?? response.statusText);
      }
      const json = await response.json();
      const pretty = JSON.stringify(json, null, 2);
      setExtractResult(pretty);
      setMapInput(pretty);
    } catch (err) {
      setExtractError(err instanceof Error ? err.message : "Extraction failed");
    }
  };

  const handleMap = async () => {
    setMapError("");
    try {
      const response = await fetch(`${API_BASE}/api/map`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: mapInput,
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail?.error ?? response.statusText);
      }
      const json = await response.json();
      const pretty = JSON.stringify(json, null, 2);
      setMapResult(pretty);
      const byField = JSON.stringify(json?.byField ?? {}, null, 2);
      setFillInput(byField);
    } catch (err) {
      setMapError(err instanceof Error ? err.message : "Mapping failed");
    }
  };

  const handleFill = async () => {
    setFillError("");
    try {
      const response = await fetch(`${API_BASE}/api/fill`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ byField: JSON.parse(fillInput || "{}") }),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail?.error ?? response.statusText);
      }
      if (response.headers.get("content-type")?.includes("application/json")) {
        const json = await response.json();
        if (json?.url) {
          window.open(json.url, "_blank");
          return;
        }
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "Completed-T1.pdf";
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setFillError(err instanceof Error ? err.message : "Fill failed");
    }
  };

  const handleProcess = async () => {
    if (!processFile) {
      setProcessError("Please choose a T4 PDF first.");
      return;
    }
    setProcessError("");
    try {
      const form = new FormData();
      form.append("file", processFile);
      const response = await fetch(`${API_BASE}/api/process`, {
        method: "POST",
        body: form,
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail?.error ?? response.statusText);
      }
      if (response.headers.get("content-type")?.includes("application/json")) {
        const json = await response.json();
        if (json?.url) {
          window.open(json.url, "_blank");
          return;
        }
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "Completed-T1.pdf";
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setProcessError(err instanceof Error ? err.message : "Process failed");
    }
  };

  return (
    <main style={{ fontFamily: "sans-serif", maxWidth: 960, margin: "0 auto", padding: "2rem" }}>
      <h1>Tax Codex – CRA 2024 Ontario</h1>

      <section style={{ marginBottom: "2rem" }}>
        <h2>1. Extract</h2>
        <input type="file" accept="application/pdf" onChange={(e) => setT4File(e.target.files?.[0] ?? null)} />
        <button onClick={handleExtract} style={{ marginLeft: "1rem" }}>Extract T4</button>
        {extractError && <p style={{ color: "red" }}>{extractError}</p>}
        {extractResult && (
          <details open>
            <summary>Extracted JSON</summary>
            <pre>{extractResult}</pre>
          </details>
        )}
      </section>

      <section style={{ marginBottom: "2rem" }}>
        <h2>2. Map</h2>
        <textarea
          value={mapInput}
          onChange={(e) => setMapInput(e.target.value)}
          rows={12}
          style={{ width: "100%" }}
          placeholder="Paste normalized JSON here"
        />
        <button onClick={handleMap}>Map to T1</button>
        {mapError && <p style={{ color: "red" }}>{mapError}</p>}
        {mapResult && (
          <details open>
            <summary>Mapped Output</summary>
            <pre>{mapResult}</pre>
          </details>
        )}
      </section>

      <section style={{ marginBottom: "2rem" }}>
        <h2>3. Fill</h2>
        <textarea
          value={fillInput}
          onChange={(e) => setFillInput(e.target.value)}
          rows={8}
          style={{ width: "100%" }}
          placeholder="Paste byField JSON here"
        />
        <button onClick={handleFill}>Fill T1 PDF</button>
        {fillError && <p style={{ color: "red" }}>{fillError}</p>}
      </section>

      <section>
        <h2>4. Process (Extract + Map + Fill)</h2>
        <input type="file" accept="application/pdf" onChange={(e) => setProcessFile(e.target.files?.[0] ?? null)} />
        <button onClick={handleProcess} style={{ marginLeft: "1rem" }}>Process T4</button>
        {processError && <p style={{ color: "red" }}>{processError}</p>}
      </section>
    </main>
  );
}

export default App;
