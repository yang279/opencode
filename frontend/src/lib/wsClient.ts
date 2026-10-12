import { getBackendInfo } from "./backend";
import type { ClientEvent, ServerEvent } from "../types/events";

type Handler = (payload: ServerEvent) => void;
export type WsStatus = "connecting" | "connected" | "disconnected";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export class WsClient {
  private ws: WebSocket | null = null;
  private handlers = new Map<string, Set<Handler>>();
  private closed = false;
  private timer: number | null = null;
  private onStatus: (s: WsStatus) => void = () => {};

  setStatusHandler(fn: (s: WsStatus) => void): void {
    this.onStatus = fn;
  }

  on(type: string, handler: Handler): () => void {
    if (!this.handlers.has(type)) this.handlers.set(type, new Set());
    this.handlers.get(type)!.add(handler);
    return () => this.handlers.get(type)?.delete(handler);
  }

  private _dispatch(e: MessageEvent): void {
    try {
      const msg = JSON.parse(e.data) as ServerEvent;
      this.handlers.get(msg.type)?.forEach((h) => h(msg));
    } catch {
      // 忽略无法解析的消息
    }
  }

  private _open(url: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(url);
      this.ws = ws;
      let settled = false;
      ws.onopen = () => {
        this.onStatus("connected");
        settled = true;
        resolve();
      };
      ws.onmessage = (e) => this._dispatch(e);
      ws.onerror = () => {
        if (!settled) {
          settled = true;
          reject(new Error("ws connect error"));
        }
      };
      ws.onclose = () => {
        this.ws = null;
        if (!settled) {
          settled = true;
          reject(new Error("ws closed before open"));
        } else {
          this.onStatus("disconnected");
          if (!this.closed) this._scheduleReconnect();
        }
      };
    });
  }

  private async _connectLoop(): Promise<void> {
    while (!this.closed) {
      try {
        const info = await getBackendInfo();
        const url = `ws://127.0.0.1:${info.port}/ws?token=${info.token}`;
        try {
          await this._open(url);
          return; // 已连接，后续断开由 onclose 触发重连
        } catch {
          await sleep(1000); // 打开失败（可能还在冷启动），稍后重试
        }
      } catch {
        this.onStatus("disconnected");
        await sleep(1000); // 后端未就绪，继续等待
      }
    }
  }

  private _scheduleReconnect(): void {
    if (this.closed || this.timer != null) return;
    this.onStatus("disconnected");
    this.timer = window.setTimeout(() => {
      this.timer = null;
      void this._connectLoop();
    }, 1000);
  }

  connect(): void {
    this.closed = false;
    void this._connectLoop();
  }

  send(payload: ClientEvent): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload));
    }
  }

  get ready(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  close(): void {
    this.closed = true;
    if (this.timer != null) {
      window.clearTimeout(this.timer);
      this.timer = null;
    }
    if (this.ws) {
      const ws = this.ws;
      this.ws = null;
      ws.onclose = null; // 防止触发重连
      ws.close();
    }
  }
}