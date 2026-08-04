import {
  clearConnectionToken,
  saveConnection,
  type ConnectionSettings,
} from "./api";

const AUTH_STORAGE_KEY = "scenara.console.auth.v1";

export function isSignedIn(): boolean {
  return (
    sessionStorage.getItem(AUTH_STORAGE_KEY) === "1" ||
    localStorage.getItem(AUTH_STORAGE_KEY) === "1"
  );
}

export function completeSignIn(
  connection: ConnectionSettings,
  remember: boolean,
): void {
  saveConnection(connection, { persistAuth: remember });
  sessionStorage.removeItem(AUTH_STORAGE_KEY);
  localStorage.removeItem(AUTH_STORAGE_KEY);
  (remember ? localStorage : sessionStorage).setItem(AUTH_STORAGE_KEY, "1");
}

export function signOut(): void {
  sessionStorage.removeItem(AUTH_STORAGE_KEY);
  localStorage.removeItem(AUTH_STORAGE_KEY);
  clearConnectionToken();
}
