import { useSyncExternalStore } from "react";

export type Toast = { id: number; type: "success" | "error" | "info"; message: string };

let _counter = 0;
let _toasts: Toast[] = [];
const _listeners = new Set<() => void>();

function _emit() {
  _toasts = [..._toasts]; // new array identity on every mutation
  _listeners.forEach((l) => l());
}

function _push(type: Toast["type"], message: string) {
  const id = ++_counter;
  _toasts = [..._toasts, { id, type, message }];
  _listeners.forEach((l) => l());
  setTimeout(() => dismiss(id), 3500);
}

export function dismiss(id: number) {
  _toasts = _toasts.filter((t) => t.id !== id);
  _emit();
}

export const toast = {
  success: (msg: string) => _push("success", msg),
  error: (msg: string) => _push("error", msg),
  info: (msg: string) => _push("info", msg),
};

const _subscribe = (cb: () => void) => {
  _listeners.add(cb);
  return () => _listeners.delete(cb);
};

const _getSnapshot = () => _toasts;

export function useToasts(): Toast[] {
  return useSyncExternalStore(_subscribe, _getSnapshot);
}
