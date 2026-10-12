import { invoke } from "@tauri-apps/api/core";

export interface BackendInfo {
  port: number;
  token: string;
}

const DEV_PORT = Number(import.meta.env.VITE_BACKEND_PORT ?? 8787);
const DEV_TOKEN = import.meta.env.VITE_BACKEND_TOKEN ?? "dev-token";

export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function getBackendInfo(): Promise<BackendInfo> {
  if (!isTauri()) {
    return { port: DEV_PORT, token: DEV_TOKEN };
  }
  // Tauri 模式下轮询等待 Rust 壳层拉起 sidecar 完成
  for (let i = 0; i < 120; i++) {
    try {
      const info = await invoke<BackendInfo | null>("get_backend_info");
      if (info) return info;
    } catch {
      // ignore
    }
    await sleep(500);
  }
  throw new Error("后端未在预期时间内就绪");
}

export async function httpBase(): Promise<string> {
  const info = await getBackendInfo();
  return `http://127.0.0.1:${info.port}`;
}