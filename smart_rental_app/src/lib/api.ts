import Constants from "expo-constants";

export type ApiResponse<T> = {
  success: boolean;
  data?: T;
  message?: string;
  count?: number;
  [key: string]: unknown;
};

const configuredUrl =
  (process.env.EXPO_PUBLIC_API_URL as string | undefined) ||
  (Constants.expoConfig?.extra?.apiUrl as string | undefined);

export const API_BASE_URL = (configuredUrl || "http://10.0.2.2:5000").replace(/\/+$/, "");

let idToken: string | null = null;

export function setIdToken(token: string | null) {
  idToken = token;
}

export function getIdToken() {
  return idToken;
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<ApiResponse<T>> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (idToken) headers.set("Authorization", `Bearer ${idToken}`);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  } catch {
    throw new Error("Không thể kết nối tới Smart Rental server. Hãy kiểm tra API URL và mạng.");
  }

  let payload: ApiResponse<T>;
  try {
    payload = await response.json();
  } catch {
    throw new Error(`Server trả về dữ liệu không hợp lệ (HTTP ${response.status}).`);
  }

  if (!response.ok || payload.success === false) {
    throw new Error(payload.message || `Request thất bại (HTTP ${response.status}).`);
  }
  return payload;
}

export function apiGet<T>(path: string) { return apiFetch<T>(path); }
export function apiPost<T>(path: string, body?: unknown) {
  return apiFetch<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
}
export function apiPut<T>(path: string, body?: unknown) {
  return apiFetch<T>(path, { method: "PUT", body: body === undefined ? undefined : JSON.stringify(body) });
}
export function apiPatch<T>(path: string, body?: unknown) {
  return apiFetch<T>(path, { method: "PATCH", body: body === undefined ? undefined : JSON.stringify(body) });
}
