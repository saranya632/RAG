import { useEffect, useRef, useState } from "react";
import { sendChatMessage } from "../services/api";

const MAX_QUESTION_LENGTH = 2000; // matches MAX_QUESTION_LENGTH in the Flask .env

let nextId = 1; // unique React keys for messages

// Sources come straight from the /chat response. Their order matches the
// [Source N] references the model writes in its answer.
function Sources({ sources }) {
  if (!sources?.length) return null;
  return (
    <div className="sources">
      <span className="sources-title">Sources</span>
      <ol>
        {sources.map((source) => (
          <li key={`${source.document_id}-${source.chunk_index}`} value={source.source_number}>
            {source.filename} — Page {source.page}
          </li>
        ))}
      </ol>
    </div>
  );
}

export default function Chat() {
  // Each message: { id, role: "user" | "assistant" | "notice" | "error", text, sources? }
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [inputError, setInputError] = useState("");
  const bottomRef = useRef(null);

  // Keep the newest message in view.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  function addMessage(message) {
    setMessages((previous) => [...previous, { id: nextId++, ...message }]);
  }

  async function handleSend(event) {
    event.preventDefault();
    const text = question.trim();
    if (!text) {
      setInputError("Please type a question.");
      return;
    }
    if (loading) return;

    setInputError("");
    setQuestion("");
    addMessage({ role: "user", text });
    setLoading(true);

    try {
      const data = await sendChatMessage(text);
      if (!data.answer?.trim()) {
        addMessage({ role: "error", text: "The assistant returned an empty answer. Please try again." });
      } else {
        addMessage({ role: "assistant", text: data.answer, sources: data.sources });
      }
    } catch (err) {
      if (err.status === 401) return; // AuthContext logs out and redirects to /login
      if (err.status === 404) {
        // "No relevant information found in the uploaded documents": a normal
        // outcome, not a failure.
        addMessage({ role: "notice", text: err.message });
      } else {
        addMessage({ role: "error", text: err.message });
      }
    } finally {
      setLoading(false);
    }
  }

  // Enter sends; Shift+Enter adds a new line.
  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) handleSend(event);
  }

  return (
    <section className="card chat-card">
      <h2>Ask your documents</h2>

      <div className="chat-messages" aria-live="polite">
        {messages.length === 0 && !loading && (
          <p className="chat-empty">Upload a PDF, then ask a question about it.</p>
        )}

        {messages.map((message) => (
          <div key={message.id} className={`message message-${message.role}`}>
            <span className="message-author">{message.role === "user" ? "You" : "Assistant"}</span>
            <p className="message-text">{message.text}</p>
            {message.role === "assistant" && <Sources sources={message.sources} />}
          </div>
        ))}

        {loading && (
          <div className="message message-assistant">
            <span className="message-author">Assistant</span>
            <p className="message-text thinking">Thinking...</p>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form className="chat-form" onSubmit={handleSend}>
        <textarea
          rows={2}
          placeholder="Ask a question..."
          value={question}
          maxLength={MAX_QUESTION_LENGTH}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
          aria-label="Question"
        />
        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading ? "..." : "Send"}
        </button>
      </form>
      {inputError && <p className="field-error">{inputError}</p>}
    </section>
  );
}
