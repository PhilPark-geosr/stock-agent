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
    searchSecurities: (options) => {
      const query = new URLSearchParams(Object.entries(options).filter(([, value]) => value != null && value !== ""));
      return request("GET", `/securities/search?${query}`);
    },
    briefingSettings: (market) => request("GET", `/briefings/settings/${encodeURIComponent(market)}`),
    briefingOptions: (market) => request("GET", `/briefings/options/${encodeURIComponent(market)}`),
    saveBriefingSettings: (market, body) => request("PUT", `/briefings/settings/${encodeURIComponent(market)}`, body),
    generateBriefing: (body) => request("POST", "/briefings", body),
    listBriefings: (offset = 0, subject = "", dates = {}) => {
      const query = new URLSearchParams({ offset: Number(offset) || 0, limit: 30, subject });
      if (dates.from) query.set("date_from", dates.from);
      if (dates.to) query.set("date_to", dates.to);
      return request("GET", `/briefings?${query}`);
    },
    briefingById: (id) => request("GET", `/briefings/${encodeURIComponent(id)}`),
    redeliverBriefing: (id, body) => request("POST", `/briefings/${encodeURIComponent(id)}/delivery`, body),
    status: () => ipcRenderer.invoke("backend:status"),
    listWatchlist: () => request("GET", "/watchlist"),
    addWatchlist: (symbol, securityId) => request("POST", "/watchlist", { symbol, security_id: securityId }),
    linkWatchlist: (id, symbol, securityId) => request("POST", `/watchlist/${encodeURIComponent(id)}/security-link`, { symbol, security_id: securityId, confirmed: true }),
    deleteWatchlist: (symbol) => request("DELETE", `/watchlist/${encodeURIComponent(symbol)}`),
    latestAnalysis: (symbol) => request("GET", `/stocks/${encodeURIComponent(symbol)}/analysis/latest`),
    runAnalysis: (symbol) => request("POST", `/stocks/${encodeURIComponent(symbol)}/analysis`),
    analysisHistory: (symbol) => request("GET", `/stocks/${encodeURIComponent(symbol)}/analysis?limit=20`),
    analysisById: (symbol, resultId) => request("GET", `/stocks/${encodeURIComponent(symbol)}/analysis/${resultId}`),
    runScheduler: () => request("POST", "/scheduler/run?force=true"),
    listAlertConditions: () => request("GET", "/alert-conditions"),
    addAlertCondition: (symbol, userRule, subscriptionId) => request("POST", "/alert-conditions", { symbol, user_rule: userRule, subscription_id: subscriptionId }),
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
