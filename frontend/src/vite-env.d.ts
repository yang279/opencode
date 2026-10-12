/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BACKEND_PORT?: string;
  readonly VITE_BACKEND_TOKEN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}