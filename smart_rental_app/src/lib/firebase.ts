import * as SecureStore from "expo-secure-store";
import { apiGet, API_BASE_URL, setIdToken } from "./api";
import { clearSession, setProfile, TenantProfile } from "./session";

const FIREBASE_API_KEY = "AIzaSyAkv604AR4Xaou0WHETZnW3-xyb4dZNXHw";
const FIREBASE_PROJECT_ID = "datn-smartrental";
const REFRESH_TOKEN_KEY = "smartrental.firebase.refreshToken";

type FirebaseSignIn = {
  idToken: string;
  refreshToken: string;
  expiresIn: string;
  localId: string;
  email: string;
  displayName?: string;
  [key: string]: unknown;
};

type FirebaseError = {
  error?: { message?: string };
};

type FirebaseRefreshResponse = {
  id_token: string;
  refresh_token: string;
  user_id: string;
  expires_in: string;
  project_id: string;
};

let currentUser: FirebaseSignIn | null = null;
const authListeners = new Set<(authenticated: boolean) => void>();

function notifyAuthState(authenticated: boolean) {
  authListeners.forEach((listener) => listener(authenticated));
}

export function onAuthStateChanged(listener: (authenticated: boolean) => void) {
  authListeners.add(listener);
  return () => authListeners.delete(listener);
}

async function saveRefreshToken(refreshToken: string) {
  await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, refreshToken);
}

async function getStoredRefreshToken() {
  return SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
}

async function clearStoredRefreshToken() {
  await SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY);
}

async function loadProfile() {
  const me = await apiGet<TenantProfile & {
    uid: string;
    email: string;
    display_name?: string;
    role?: string;
  }>("/api/auth/me");

  return me.data;
}

export async function signIn(email: string, password: string) {
  const response = await fetch(
    `https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=${FIREBASE_API_KEY}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email,
        password,
        returnSecureToken: true,
      }),
    }
  );

  const payload = (await response.json()) as FirebaseSignIn & FirebaseError;

  if (!response.ok || !payload.idToken || !payload.refreshToken) {
    const code = payload.error?.message || "LOGIN_FAILED";
    const messages: Record<string, string> = {
      INVALID_LOGIN_CREDENTIALS: "Email hoặc mật khẩu không đúng.",
      EMAIL_NOT_FOUND: "Email chưa được đăng ký.",
      INVALID_PASSWORD: "Mật khẩu không đúng.",
      USER_DISABLED: "Tài khoản đã bị vô hiệu hóa.",
      TOO_MANY_ATTEMPTS_TRY_LATER: "Có quá nhiều lần đăng nhập. Hãy thử lại sau.",
    };
    throw new Error(messages[code] || `Đăng nhập Firebase thất bại: ${code}`);
  }

  currentUser = payload;
  setIdToken(payload.idToken);
  await saveRefreshToken(payload.refreshToken);

  try {
    const profile = await loadProfile();
    setProfile(profile || null);

    notifyAuthState(profile?.role === "tenant");

    return {
      firebase: payload,
      profile,
    };
  } catch (error) {
    setIdToken(null);
    currentUser = null;
    await clearStoredRefreshToken();
    clearSession();
    throw error;
  }
}

/**
 * Khôi phục phiên đăng nhập khi app được mở lại.
 *
 * Firebase ID token chỉ có thời hạn ngắn, vì vậy app lưu refresh token
 * trong SecureStore và dùng refresh token để lấy ID token mới thay vì
 * bắt người dùng nhập lại email/mật khẩu.
 */
export async function restoreSession() {
  const storedRefreshToken = await getStoredRefreshToken();

  if (!storedRefreshToken) {
    return null;
  }

  try {
    const response = await fetch(
      `https://securetoken.googleapis.com/v1/token?key=${FIREBASE_API_KEY}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body:
          `grant_type=refresh_token&refresh_token=${encodeURIComponent(
            storedRefreshToken
          )}`,
      }
    );

    const payload = (await response.json()) as FirebaseRefreshResponse & FirebaseError;

    if (!response.ok || !payload.id_token || !payload.refresh_token) {
      throw new Error(payload.error?.message || "SESSION_EXPIRED");
    }

    const restoredUser: FirebaseSignIn = {
      idToken: payload.id_token,
      refreshToken: payload.refresh_token,
      expiresIn: payload.expires_in,
      localId: payload.user_id,
      email: "",
    };

    currentUser = restoredUser;
    setIdToken(payload.id_token);

    // Firebase có thể cấp refresh token mới sau mỗi lần refresh.
    await saveRefreshToken(payload.refresh_token);

    const profile = await loadProfile();
    setProfile(profile || null);

    notifyAuthState(profile?.role === "tenant");

    return {
      firebase: restoredUser,
      profile,
    };
  } catch (error) {
    console.warn("[auth] restore session failed", error);
    currentUser = null;
    setIdToken(null);
    clearSession();
    await clearStoredRefreshToken();
    notifyAuthState(false);
    return null;
  }
}

export async function signOut() {
  currentUser = null;
  setIdToken(null);
  clearSession();
  await clearStoredRefreshToken();
  notifyAuthState(false);

  // Backend xác nhận logout nhưng không giữ session server-side.
  try {
    await fetch(`${API_BASE_URL}/api/auth/logout`, { method: "POST" });
  } catch {
    // Logout client-side vẫn thành công nếu server không reachable.
  }
}

export function getCurrentFirebaseUser() {
  return currentUser;
}

export { FIREBASE_PROJECT_ID };
