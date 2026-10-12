import "@testing-library/jest-dom/vitest";

// antd (v5) 依赖 window.matchMedia，jsdom 未实现，这里提供最小 mock
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});