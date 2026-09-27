import { useRef, useState } from "react";
import { uploadPdf } from "../services/api";

const MAX_SIZE_MB = 50; // matches MAX_CONTENT_LENGTH in the Flask .env

function isPdf(file) {
  return file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
}

export default function FileUpload() {
  const [file, setFile] = useState(null);
  // "idle" | "uploading" | "success" | "error"
  const [status, setStatus] = useState("idle");
  const [message, setMessage] = useState("");
  const inputRef = useRef(null);

  function handleSelect(event) {
    const selected = event.target.files[0] ?? null;
    setFile(selected);
    setStatus("idle");
    setMessage("");
    if (selected && !isPdf(selected)) {
      setStatus("error");
      setMessage("Please choose a PDF file (.pdf).");
    }
  }

  async function handleUpload() {
    if (!file) {
      setStatus("error");
      setMessage("Please select a PDF file first.");
      return;
    }
    if (!isPdf(file)) {
      setStatus("error");
      setMessage("Please choose a PDF file (.pdf).");
      return;
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      setStatus("error");
      setMessage(`The file is larger than ${MAX_SIZE_MB} MB.`);
      return;
    }

    setStatus("uploading");
    setMessage("");
    try {
      const data = await uploadPdf(file);
      setStatus("success");
      // Only user-relevant details; no document IDs or chunk counts.
      setMessage(
        `PDF uploaded and processed successfully: ${data.filename} (${data.page_count} ${data.page_count === 1 ? "page" : "pages"}).`
      );
      setFile(null);
      inputRef.current.value = ""; // clear the file picker
    } catch (err) {
      // 401 is handled globally (logout + redirect); other errors show here,
      // e.g. "Invalid file: content is not a valid PDF" (415).
      setStatus("error");
      setMessage(`Upload failed: ${err.message}`);
    }
  }

  const uploading = status === "uploading";

  return (
    <section className="card upload-card">
      <h2>Upload a PDF</h2>
      <p className="hint">The document is added to the knowledge base so you can ask questions about it.</p>

      <label htmlFor="pdf-file" className="file-label">Select PDF</label>
      <input
        id="pdf-file"
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        onChange={handleSelect}
        disabled={uploading}
      />

      <p className="selected-file">
        Selected file: <strong>{file ? file.name : "none"}</strong>
      </p>

      <button type="button" className="btn btn-primary" onClick={handleUpload} disabled={uploading || !file}>
        {uploading ? "Uploading..." : "Upload PDF"}
      </button>

      {uploading && (
        <p className="alert alert-info">Uploading and processing... large PDFs can take a minute.</p>
      )}
      {status === "success" && <p className="alert alert-success">{message}</p>}
      {status === "error" && <p className="alert alert-error" role="alert">{message}</p>}
    </section>
  );
}
