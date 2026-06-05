import { useEffect, useRef, useState, type ChangeEvent, type KeyboardEvent } from "react";
import {
  checkHealth,
  createChat,
  deleteUploadedKnowledgeFile,
  getChat,
  listChats,
  listUploadedKnowledgeFiles,
  queryBrain,
  type CitationItem,
  type ChatMessageItem,
  type ChatSummary,
  type QueryFilters,
  type QueryResponse,
  type UploadFileItem,
  uploadKnowledgeFile,
} from "./api";
import "./App.css";

interface Message {
  id?: number;
  role: "user" | "assistant";
  content: string;
  citations?: CitationItem[];
  created_at?: string;
}

const ACTIVE_CHAT_STORAGE_KEY = "synced-brain-active-chat-id";

function SourceBadge({ source }: { source: string }) {
  const parts = source.split("/");
  const filename = parts[parts.length - 1];
  return (
    <span className="source-badge" title={source}>
      📄 {filename}
    </span>
  );
}

function CitationCard({ citation, index }: { citation: CitationItem; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const preview = citation.text.slice(0, 160);

  return (
    <div className="citation-card">
      <div className="citation-header">
        <span className="citation-index">[{index + 1}]</span>
        <SourceBadge source={citation.source} />
        {citation.page && citation.page > 0 && <span className="citation-page">p.{citation.page}</span>}
      </div>
      <p className="citation-text">
        {expanded ? citation.text : preview}
        {citation.text.length > 160 && (
          <button className="expand-btn" onClick={() => setExpanded(!expanded)}>
            {expanded ? " show less" : "… show more"}
          </button>
        )}
      </p>
    </div>
  );
}

function formatChatTime(timestamp: string) {
  return new Date(timestamp).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function mapChatMessages(messages: ChatMessageItem[]): Message[] {
  return messages.map((message) => ({
    id: message.id,
    role: message.role,
    content: message.content,
    citations: message.citations as unknown as CitationItem[],
    created_at: message.created_at,
  }));
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [historySidebarCollapsed, setHistorySidebarCollapsed] = useState(() => {
    return localStorage.getItem("synced-brain-history-collapsed") === "true";
  });
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    return localStorage.getItem("synced-brain-control-collapsed") === "true";
  });

  const toggleHistorySidebar = () => {
    setHistorySidebarCollapsed((prev) => {
      const newVal = !prev;
      localStorage.setItem("synced-brain-history-collapsed", String(newVal));
      return newVal;
    });
  };

  const toggleSidebar = () => {
    setSidebarCollapsed((prev) => {
      const newVal = !prev;
      localStorage.setItem("synced-brain-control-collapsed", String(newVal));
      return newVal;
    });
  };

  const [loading, setLoading] = useState(false);
  const [loadingChats, setLoadingChats] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [healthy, setHealthy] = useState<boolean | null>(null);
  const [topK, setTopK] = useState(5);
  const [debugMode, setDebugMode] = useState(false);
  const [filterDocType, setFilterDocType] = useState<"" | "md" | "pdf">("");
  const [filterPrefix, setFilterPrefix] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState("");
  const [uploadedFiles, setUploadedFiles] = useState<UploadFileItem[]>([]);
  const [uploadsLoading, setUploadsLoading] = useState(false);
  const [deletingFilename, setDeletingFilename] = useState<string | null>(null);
  const [chatSummaries, setChatSummaries] = useState<ChatSummary[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [activeChatTitle, setActiveChatTitle] = useState("New chat");
  const [chatError, setChatError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  async function refreshUploads() {
    setUploadsLoading(true);
    try {
      const res = await listUploadedKnowledgeFiles();
      setUploadedFiles(res.files);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setUploadStatus(`List uploads error: ${msg}`);
    } finally {
      setUploadsLoading(false);
    }
  }

  async function loadChat(chatId: string) {
    setLoadingMessages(true);
    setChatError("");

    try {
      const res = await getChat(chatId);
      setMessages(mapChatMessages(res.messages));
      setActiveChatId(res.chat.id);
      setActiveChatTitle(res.chat.title);
      localStorage.setItem(ACTIVE_CHAT_STORAGE_KEY, res.chat.id);
      setChatSummaries((prev) => {
        const filtered = prev.filter((chat) => chat.id !== res.chat.id);
        return [
          {
            ...res.chat,
            last_message_preview: res.chat.last_message_preview ?? res.messages[res.messages.length - 1]?.content ?? null,
          },
          ...filtered,
        ];
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setChatError(`Open chat error: ${msg}`);
    } finally {
      setLoadingMessages(false);
    }
  }

  async function syncChats(preferredChatId?: string) {
    setLoadingChats(true);
    setChatError("");

    try {
      const res = await listChats();
      setChatSummaries(res.chats);

      const storedChatId = preferredChatId ?? localStorage.getItem(ACTIVE_CHAT_STORAGE_KEY) ?? undefined;
      const preferredChat = storedChatId ? res.chats.find((chat) => chat.id === storedChatId) : undefined;

      if (preferredChat) {
        setActiveChatId(preferredChat.id);
        setActiveChatTitle(preferredChat.title);
        return preferredChat.id;
      }

      if (res.chats.length > 0) {
        await loadChat(res.chats[0].id);
        return res.chats[0].id;
      }

      const created = await createChat();
      setChatSummaries([created]);
      await loadChat(created.id);
      return created.id;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setChatError(`Chat load error: ${msg}`);
      return undefined;
    } finally {
      setLoadingChats(false);
    }
  }

  async function handleNewChat() {
    if (loading || loadingMessages) return;

    setChatError("");
    try {
      const created = await createChat();
      setChatSummaries((prev) => [created, ...prev.filter((chat) => chat.id !== created.id)]);
      setActiveChatId(created.id);
      setActiveChatTitle(created.title);
      setMessages([]);
      localStorage.setItem(ACTIVE_CHAT_STORAGE_KEY, created.id);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setChatError(`Create chat error: ${msg}`);
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      const healthyResult = await checkHealth();
      if (cancelled) return;

      setHealthy(healthyResult);
      await syncChats();
      await refreshUploads();
    }

    void bootstrap();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSend() {
    const q = input.trim();
    if (!q || loading) return;

    let chatId = activeChatId;
    if (!chatId) {
      const created = await createChat();
      chatId = created.id;
      setChatSummaries((prev) => [created, ...prev.filter((chat) => chat.id !== created.id)]);
      setActiveChatId(created.id);
      setActiveChatTitle(created.title);
      setMessages([]);
      localStorage.setItem(ACTIVE_CHAT_STORAGE_KEY, created.id);
    }

    setMessages((prev) => [...prev, { role: "user", content: q }]);
    setInput("");
    setLoading(true);

    const filters: QueryFilters = {};
    if (filterPrefix) filters.source_prefix = filterPrefix;
    if (filterDocType) filters.doc_type = filterDocType;

    try {
      const res: QueryResponse = await queryBrain(
        q,
        topK,
        Object.keys(filters).length ? filters : undefined,
        debugMode,
        chatId,
      );

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.answer,
          citations: res.citations,
        },
      ]);
      setActiveChatId(res.chat_id);
      setActiveChatTitle(res.chat_title);
      localStorage.setItem(ACTIVE_CHAT_STORAGE_KEY, res.chat_id);
      await syncChats(res.chat_id);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setMessages((prev) => [...prev, { role: "assistant", content: `⚠️ Error: ${msg}` }]);
      setChatError(`Query failed: ${msg}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleUploadChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || uploading) return;

    setUploading(true);
    setUploadStatus("Uploading and syncing...");

    try {
      const res = await uploadKnowledgeFile(file);
      setUploadStatus(`Uploaded: ${res.action}, chunks: ${res.chunks}`);
      setFilterPrefix("knowledge/uploads/");
      await refreshUploads();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setUploadStatus(`Upload error: ${msg}`);
    } finally {
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  }

  async function handleDeleteUpload(file: UploadFileItem) {
    if (deletingFilename || uploading) return;
    const confirmed = window.confirm(`Delete ${file.name}? This will remove synced chunks too.`);
    if (!confirmed) return;

    setDeletingFilename(file.name);
    setUploadStatus(`Deleting ${file.name} and syncing...`);

    try {
      const res = await deleteUploadedKnowledgeFile(file.name);
      setUploadStatus(`Deleted: ${res.action}`);
      await refreshUploads();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setUploadStatus(`Delete error: ${msg}`);
    } finally {
      setDeletingFilename(null);
    }
  }

  const activeChat = chatSummaries.find((chat) => chat.id === activeChatId) ?? null;

  return (
    <div className="app-shell">
      <aside className={`history-sidebar ${historySidebarCollapsed ? "collapsed" : ""}`}>
        <div className="history-sidebar-inner">
          <div className="sidebar-logo history-logo">
            <span className="logo-icon">🧠</span>
            <div>
              <span className="logo-text">Synced Brain</span>
              <p className="sidebar-subtitle">Conversation archive</p>
            </div>
          </div>

          <div className="history-actions">
            <button className="new-chat-btn" onClick={() => void handleNewChat()}>
              + New chat
            </button>
            <p className="history-note">Select a previous thread or continue the active one.</p>
          </div>

          <div className="sidebar-status history-status">
            <span className={`status-dot ${healthy === null ? "checking" : healthy ? "ok" : "err"}`} />
            {healthy === null ? "Connecting…" : healthy ? "Backend online" : "Backend offline"}
          </div>

          <section className="chat-list-panel">
            <div className="chat-list-header">
              <span>Previous chats</span>
              <span>{loadingChats ? "Loading…" : `${chatSummaries.length}`}</span>
            </div>

            {chatError && <p className="chat-error-banner">{chatError}</p>}

            <div className="chat-list">
              {loadingChats && chatSummaries.length === 0 ? (
                <p className="chat-list-empty">Loading conversations…</p>
              ) : chatSummaries.length === 0 ? (
                <p className="chat-list-empty">No saved chats yet.</p>
              ) : (
                chatSummaries.map((chat) => {
                  const preview = chat.last_message_preview ?? "Start typing to create the first message.";
                  return (
                    <button
                      key={chat.id}
                      className={`chat-list-item ${chat.id === activeChatId ? "active" : ""}`}
                      onClick={() => void loadChat(chat.id)}
                    >
                      <div className="chat-list-item-top">
                        <span className="chat-list-title">{chat.title}</span>
                        <span className="chat-list-count">{chat.message_count}</span>
                      </div>
                      <p className="chat-list-preview">{preview}</p>
                      <span className="chat-list-time">{formatChatTime(chat.updated_at)}</span>
                    </button>
                  );
                })
              )}
            </div>
          </section>
        </div>
      </aside>

      <main className="chat-area">
        <div className="chat-area-header">
          <div className="chat-area-header-left">
            <button
              className={`sidebar-toggle-btn left ${historySidebarCollapsed ? "collapsed" : ""}`}
              onClick={toggleHistorySidebar}
              title={historySidebarCollapsed ? "Expand history" : "Collapse history"}
              aria-label="Toggle History Sidebar"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                <line x1="9" y1="3" x2="9" y2="21"/>
              </svg>
            </button>
            <div className="chat-title-group">
              <p className="chat-kicker">Conversation</p>
              <h1>{activeChat?.title ?? activeChatTitle}</h1>
            </div>
          </div>
          <div className="chat-header-meta">
            <span>{messages.length} messages</span>
            {loadingMessages && <span>Loading thread…</span>}
            <button
              className={`sidebar-toggle-btn right ${sidebarCollapsed ? "collapsed" : ""}`}
              onClick={toggleSidebar}
              title={sidebarCollapsed ? "Expand control panel" : "Collapse control panel"}
              aria-label="Toggle Control Panel Sidebar"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                <line x1="15" y1="3" x2="15" y2="21"/>
              </svg>
            </button>
          </div>
        </div>

        <div className="messages">
          {messages.length === 0 && !loadingMessages && (
            <div className="empty-state">
              <span className="empty-icon">🧠</span>
              <h2>Your Synced Brain</h2>
              <p>Ask anything about your knowledge base. Each chat is saved, and previous threads are listed on the left.</p>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={msg.id ?? i} className={`message ${msg.role}`}>
              <div className="message-bubble">
                <span className="message-role">{msg.role === "user" ? "You" : "Brain"}</span>
                <p className="message-content">{msg.content}</p>
              </div>

              {msg.role === "assistant" && msg.citations && msg.citations.length > 0 && (
                <div className="citations-block">
                  <p className="citations-label">Sources ({msg.citations.length})</p>
                  <div className="citations-list">
                    {msg.citations.map((citation, citationIndex) => (
                      <CitationCard key={citationIndex} citation={citation} index={citationIndex} />
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="message assistant">
              <div className="message-bubble">
                <span className="message-role">Brain</span>
                <p className="message-content thinking">
                  <span />
                  <span />
                  <span />
                </p>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="input-bar">
          <textarea
            className="input-field"
            rows={1}
            placeholder="Ask your brain anything… (Enter to send, Shift+Enter for newline)"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => handleKeyDown(e)}
            disabled={loading}
          />
          <button className="send-btn" onClick={() => void handleSend()} disabled={loading || !input.trim()}>
            {loading ? "…" : "Ask"}
          </button>
        </div>
      </main>

      <aside className={`sidebar ${sidebarCollapsed ? "collapsed" : ""}`}>
        <div className="sidebar-inner">
          <div className="sidebar-logo">
            <span className="logo-icon">🧭</span>
            <span className="logo-text">Control panel</span>
          </div>

          <div className="sidebar-status">
            <span className={`status-dot ${healthy === null ? "checking" : healthy ? "ok" : "err"}`} />
            {healthy === null ? "Connecting…" : healthy ? "Backend online" : "Backend offline"}
          </div>

          <section className="sidebar-section">
            <label className="sidebar-label">Active chat</label>
            <div className="active-chat-card">
              <span className="active-chat-title">{activeChat?.title ?? activeChatTitle}</span>
              <span className="active-chat-meta">{messages.length} messages</span>
            </div>
          </section>

          <section className="sidebar-section">
            <label className="sidebar-label">Results (top-k)</label>
            <input
              type="number"
              min={1}
              max={20}
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              className="sidebar-input"
            />
          </section>

          <section className="sidebar-section">
            <label className="sidebar-label">Filter: doc type</label>
            <select
              value={filterDocType}
              onChange={(e) => setFilterDocType(e.target.value as "" | "md" | "pdf")}
              className="sidebar-input"
            >
              <option value="">All</option>
              <option value="md">Markdown</option>
              <option value="pdf">PDF</option>
            </select>
          </section>

          <section className="sidebar-section">
            <label className="sidebar-label">Filter: path prefix</label>
            <input
              type="text"
              placeholder="knowledge/ops/"
              value={filterPrefix}
              onChange={(e) => setFilterPrefix(e.target.value)}
              className="sidebar-input"
            />
          </section>

          <section className="sidebar-section">
            <label className="sidebar-toggle">
              <input
                type="checkbox"
                checked={debugMode}
                onChange={(e) => setDebugMode(e.target.checked)}
              />
              <span>Debug scores</span>
            </label>
          </section>

          <section className="sidebar-section">
            <label className="sidebar-label">Upload to knowledge</label>
            <input
              ref={fileInputRef}
              type="file"
              accept=".md,.txt,.pdf"
              onChange={handleUploadChange}
              className="hidden-file-input"
            />
            <button
              className="sidebar-upload-btn"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              {uploading ? "Uploading..." : "Upload File"}
            </button>

            <div className="upload-files-block">
              <div className="upload-files-header">
                <span>Uploaded Files</span>
                <button
                  className="upload-files-refresh"
                  onClick={() => void refreshUploads()}
                  disabled={uploadsLoading || uploading || !!deletingFilename}
                >
                  {uploadsLoading ? "Loading..." : "Refresh"}
                </button>
              </div>

              {uploadsLoading ? (
                <p className="upload-files-empty">Loading files...</p>
              ) : uploadedFiles.length === 0 ? (
                <p className="upload-files-empty">No uploaded files yet.</p>
              ) : (
                <ul className="upload-files-list">
                  {uploadedFiles.map((file) => (
                    <li key={file.name} className="upload-file-item">
                      <div className="upload-file-meta">
                        <span className="upload-file-name" title={file.name}>{file.name}</span>
                        <span className="upload-file-size">{Math.max(1, Math.round(file.size_bytes / 1024))} KB</span>
                      </div>
                      <button
                        className="upload-file-delete-btn"
                        onClick={() => void handleDeleteUpload(file)}
                        disabled={uploading || !!deletingFilename}
                      >
                        {deletingFilename === file.name ? "Deleting..." : "Delete"}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {uploadStatus && <p className="upload-status">{uploadStatus}</p>}
          </section>

          <div className="sidebar-footer">
            <p>Uploads are saved as markdown in <code>knowledge/uploads/</code> and synced immediately.</p>
          </div>
        </div>
      </aside>
    </div>
  );

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  }
}
