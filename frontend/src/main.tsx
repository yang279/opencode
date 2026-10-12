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
          colorPrimary: "#d97757",
          colorInfo: "#d97757",
          colorLink: "#c96442",
          colorTextBase: "#1f1e1d",
          colorBgLayout: "#faf9f5",
          colorBgContainer: "#ffffff",
          colorBorder: "#e8e6dc",
          colorBorderSecondary: "#eeece3",
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