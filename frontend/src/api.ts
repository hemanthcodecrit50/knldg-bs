const BACKEND_URL = import.meta.env.VITE_BACKEND_URL;

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
  retrieval?: { top_k: number; scores: number[] } | null;
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
  debug = false
): Promise<QueryResponse> {
  const res = await fetch(`${BACKEND_URL}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, top_k: topK, filters, debug }),
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
