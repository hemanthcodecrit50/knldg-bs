const BACKEND_URL = (import.meta.env.VITE_BACKEND_URL || "/api").replace(/\/$/, "");

export interface CitationItem {
  source: string;
  chunk_index: number;
  text: string;
  page: number | null;
  score?: number | null;
}

export interface QueryResponse {
  answer: string;
  citations: CitationItem[];
  chat_id: string;
  chat_title: string;
  retrieval?: { top_k: number; scores: number[] } | null;
}

export interface ChatSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message_preview?: string | null;
}

export interface ChatMessageItem {
  id: number;
  chat_id: string;
  role: "user" | "assistant";
  content: string;
  citations: Record<string, unknown>[];
  created_at: string;
}

export interface ChatDetailResponse {
  chat: ChatSummary;
  messages: ChatMessageItem[];
}

export interface ChatListResponse {
  status: string;
  chats: ChatSummary[];
}

export interface QueryFilters {
  source_prefix?: string;
  doc_type?: "md" | "pdf";
}

export interface UploadResponse {
  status: string;
  source: string;
  action: "ADDED" | "MODIFIED" | "UNCHANGED";
  chunks: number;
}

export interface UploadFileItem {
  name: string;
  source: string;
  size_bytes: number;
  modified_at: string;
}

export interface UploadListResponse {
  status: string;
  files: UploadFileItem[];
}

export interface DeleteUploadResponse {
  status: string;
  source: string;
  action: "DELETED";
  chunks: number;
}

export async function queryBrain(
  question: string,
  topK = 5,
  filters?: QueryFilters,
  debug = false,
  chatId?: string
): Promise<QueryResponse> {
  const res = await fetch(`${BACKEND_URL}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, top_k: topK, filters, debug, chat_id: chatId }),
  });
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Query failed (${res.status}): ${errText}`);
  }
  return res.json();
}

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${BACKEND_URL}/health`);
    return res.ok;
  } catch {
    return false;
  }
}

export async function listChats(): Promise<ChatListResponse> {
  const res = await fetch(`${BACKEND_URL}/chats`);
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`List chats failed (${res.status}): ${errText}`);
  }
  return res.json();
}

export async function createChat(title?: string): Promise<ChatSummary> {
  const res = await fetch(`${BACKEND_URL}/chats`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(title ? { title } : {}),
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Create chat failed (${res.status}): ${errText}`);
  }

  return res.json();
}

export async function getChat(chatId: string): Promise<ChatDetailResponse> {
  const encoded = encodeURIComponent(chatId);
  const res = await fetch(`${BACKEND_URL}/chats/${encoded}`);
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Get chat failed (${res.status}): ${errText}`);
  }
  return res.json();
}

export async function uploadKnowledgeFile(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${BACKEND_URL}/upload`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Upload failed (${res.status}): ${errText}`);
  }

  return res.json();
}

export async function listUploadedKnowledgeFiles(): Promise<UploadListResponse> {
  const res = await fetch(`${BACKEND_URL}/uploads`);
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`List uploads failed (${res.status}): ${errText}`);
  }
  return res.json();
}

export async function deleteUploadedKnowledgeFile(
  filename: string
): Promise<DeleteUploadResponse> {
  const encoded = encodeURIComponent(filename);
  const res = await fetch(`${BACKEND_URL}/uploads/${encoded}`, {
    method: "DELETE",
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Delete upload failed (${res.status}): ${errText}`);
  }

  return res.json();
}
