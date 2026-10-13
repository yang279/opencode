import React from "react";
import ReactDOM from "react-dom/client";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import App from "./App";
import { api } from "./lib/api";
import "./styles.css";

function reportCrash(message: string, stack?: string, source?: string) {
  api
    .reportCrash({ message, stack, source })
    .catch(() => {});
}

window.addEventListener("error", (e) => {
  reportCrash(e.message || "unknown error", e.error?.stack, "window");
});

window.addEventListener("unhandledrejection", (e) => {
  const reason = e.reason;
  const message = reason instanceof Error ? reason.message : String(reason);
  const stack = reason instanceof Error ? reason.stack : undefined;
  reportCrash(message, stack, "unhandledrejection");
});

const fontFamily =
  '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif';

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: "#5b5bd6",
          colorInfo: "#5b5bd6",
          colorLink: "#4f46e5",
          colorTextBase: "#1c1d26",
          colorBgLayout: "#f7f7fb",
          colorBgContainer: "#ffffff",
          colorBorder: "#e4e5ee",
          colorBorderSecondary: "#d2d3e0",
          borderRadius: 8,
          fontFamily,
        },
        components: {
          Button: { borderRadius: 10, fontWeight: 500 },
          Input: { borderRadius: 12 },
          Modal: { borderRadius: 16 },
          Tag: { borderRadiusSM: 6 },
        },
      }}
    >
      <App />
    </ConfigProvider>
  </React.StrictMode>,
);