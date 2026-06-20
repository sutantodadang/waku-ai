import { useSyncExternalStore } from "react";

const TOKEN_KEY = "waku_token";
const NAME_KEY = "waku_business";

let token: string | null = localStorage.getItem(TOKEN_KEY);
let businessName: string | null = localStorage.getItem(NAME_KEY);
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}

export const authStore = {
  getToken: () => token,
  getBusinessName: () => businessName,
  setSession(newToken: string, name: string | null) {
    token = newToken;
    businessName = name;
    localStorage.setItem(TOKEN_KEY, newToken);
    if (name) localStorage.setItem(NAME_KEY, name);
    else localStorage.removeItem(NAME_KEY);
    emit();
  },
  setBusinessName(name: string) {
    businessName = name;
    localStorage.setItem(NAME_KEY, name);
    emit();
  },
  clear() {
    token = null;
    businessName = null;
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(NAME_KEY);
    emit();
  },
  subscribe(l: () => void) {
    listeners.add(l);
    return () => listeners.delete(l);
  },
};

export function useAuth() {
  const t = useSyncExternalStore(authStore.subscribe, authStore.getToken);
  const name = useSyncExternalStore(authStore.subscribe, authStore.getBusinessName);
  return { token: t, businessName: name };
}
