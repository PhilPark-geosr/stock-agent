const { contextBridge, ipcRenderer } = require("electron");

const request = (method, requestPath, body) => ipcRenderer.invoke("backend:request", {
  method,
  requestPath,
  body
});

contextBridge.exposeInMainWorld("desktop", {
  platform: process.platform,
  versions: {
    electron: process.versions.electron,
    chrome: process.versions.chrome
  },
  backend: {
    status: () => ipcRenderer.invoke("backend:status"),
    listWatchlist: () => request("GET", "/watchlist"),
    addWatchlist: (symbol) => request("POST", "/watchlist", { symbol }),
    deleteWatchlist: (symbol) => request("DELETE", `/watchlist/${encodeURIComponent(symbol)}`),
    latestAnalysis: (symbol) => request("GET", `/stocks/${encodeURIComponent(symbol)}/analysis/latest`),
    runAnalysis: (symbol) => request("POST", `/stocks/${encodeURIComponent(symbol)}/analysis`),
    analysisHistory: (symbol) => request("GET", `/stocks/${encodeURIComponent(symbol)}/analysis?limit=20`),
    analysisById: (symbol, resultId) => request("GET", `/stocks/${encodeURIComponent(symbol)}/analysis/${resultId}`),
    runScheduler: () => request("POST", "/scheduler/run?force=true"),
    listAlertConditions: () => request("GET", "/alert-conditions"),
    addAlertCondition: (symbol, userRule) => request("POST", "/alert-conditions", { symbol, user_rule: userRule }),
    deleteAlertCondition: (conditionId) => request("DELETE", `/alert-conditions/${conditionId}`)
  },
  auth: {
    restore: () => ipcRenderer.invoke("auth:restore"),
    login: () => ipcRenderer.invoke("auth:login"),
    logout: () => ipcRenderer.invoke("auth:logout"),
    onExpired: (callback) => {
      const handler = () => callback();
      ipcRenderer.on("auth:expired", handler);
      return () => ipcRenderer.removeListener("auth:expired", handler);
    }
  },
  notifications: {
    connect: () => ipcRenderer.invoke("notifications:connect"),
    status: () => ipcRenderer.invoke("notifications:status"),
    disconnect: () => ipcRenderer.invoke("notifications:disconnect")
  }
});
