const baseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8001";

export type ApiError = {
  message: string;
  status?: number;
};

async function safeJson<T>(response: Response): Promise<T> {
  const text = await response.text();
  if (!text) {
    return {} as T;
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    throw { message: "Failed to parse JSON response." } as ApiError;
  }
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      ...options,
    });

    if (!response.ok) {
      const payload = await safeJson<Record<string, unknown>>(response).catch(() => ({}));
      const detail =
        payload && typeof payload === "object" && "detail" in payload
          ? (payload as Record<string, unknown>)["detail"]
          : null;
      const message = detail ? String(detail) : `Request failed (${response.status}).`;
      throw { message, status: response.status } as ApiError;
    }

    return safeJson<T>(response);
  } catch (error) {
    if ((error as ApiError).message) {
      throw error;
    }
    throw { message: "Network error. Please check the API server." } as ApiError;
  }
}
