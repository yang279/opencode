import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";

const BLUR_KEY = "myopencode.bg.blur";
const DARK_KEY = "myopencode.bg.dark";

function readNum(key: string, def: number): number {
  try {
    const v = Number(localStorage.getItem(key));
    if (Number.isFinite(v)) return v;
  } catch {
    // ignore
  }
  return def;
}

export interface BackgroundState {
  dataUrl: string | null;
  blur: number;
  dark: number;
  loaded: boolean;
  setBlur: (v: number) => void;
  setDark: (v: number) => void;
  upload: (file: File) => Promise<void>;
  remove: () => Promise<void>;
}

export function useBackground(): BackgroundState {
  const [dataUrl, setDataUrl] = useState<string | null>(null);
  const [blur, setBlurState] = useState<number>(() => readNum(BLUR_KEY, 0));
  const [dark, setDarkState] = useState<number>(() => readNum(DARK_KEY, 0));
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    api
      .getBackground()
      .then((r) => setDataUrl(r.exists ? r.data_url : null))
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  const setBlur = useCallback((v: number) => {
    setBlurState(v);
    try {
      localStorage.setItem(BLUR_KEY, String(v));
    } catch {
      // ignore
    }
  }, []);

  const setDark = useCallback((v: number) => {
    setDarkState(v);
    try {
      localStorage.setItem(DARK_KEY, String(v));
    } catch {
      // ignore
    }
  }, []);

  const upload = useCallback(async (file: File) => {
    const res = await api.uploadBackground(file);
    if (!res.ok) throw new Error(res.error || "上传失败");
    const r = await api.getBackground();
    setDataUrl(r.exists ? r.data_url : null);
  }, []);

  const remove = useCallback(async () => {
    await api.deleteBackground();
    setDataUrl(null);
  }, []);

  return { dataUrl, blur, dark, loaded, setBlur, setDark, upload, remove };
}
