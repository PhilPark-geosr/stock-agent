const { app, BrowserWindow, ipcMain, safeStorage, shell } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const { createAuthenticatedRequester, createSessionStore } = require("./lib/auth-session");
const { createLoginFlow } = require("./lib/login-flow");
const { createNotificationFlow } = require("./lib/notification-flow");

const API_BASE_URL = process.env.STOCK_AGENT_API_URL || "http://127.0.0.1:8000";
const repositoryRoot = path.resolve(__dirname, "..");
let backendProcess = null;
let mainWindow = null;
let sessionStore = null;
let authenticatedRequest = null;
let loginFlow = null;
let notificationFlow = null;

function pythonCommand() {
  const candidates = process.platform === "win32"
    ? [
        path.join(repositoryRoot, ".venv", "Scripts", "python.exe"),
        path.join(repositoryRoot, ".python311", "python.exe")
      ]
    : [path.join(repositoryRoot, ".venv", "bin", "python")];
  return candidates.find((candidate) => fs.existsSync(candidate)) || "python";
}

async function backendIsReady() {
  try {
    const response = await fetch(`${API_BASE_URL}/health`, { signal: AbortSignal.timeout(1200) });
    return response.ok;
  } catch {
    return false;
  }
}

async function ensureBackend() {
  if (await backendIsReady()) return;
  if (!backendProcess) {
    backendProcess = spawn(
      pythonCommand(),
      ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
      {
        cwd: repositoryRoot,
        env: { ...process.env, PYTHONUNBUFFERED: "1" },
        stdio: "ignore",
        windowsHide: true
      }
    );
    backendProcess.once("exit", () => {
      backendProcess = null;
    });
  }

  for (let attempt = 0; attempt < 30; attempt += 1) {
    if (await backendIsReady()) return;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error("FastAPI backend did not become ready");
}

async function rawBackendRequest(requestPath, { method = "GET", body, timeout = 120000 } = {}) {
  if (typeof requestPath !== "string" || !requestPath.startsWith("/")) {
    throw new Error("Invalid backend request path");
  }
  await ensureBackend();
  const response = await fetch(`${API_BASE_URL}${requestPath}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeout)
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail = typeof payload?.detail === "string" ? payload.detail : JSON.stringify(payload?.detail || payload);
    throw new Error(detail || `Backend request failed (${response.status})`);
  }
  return { status: response.status, payload };
}

async function requestBackend({ method = "GET", requestPath, body }) {
  if (typeof requestPath !== "string" || !requestPath.startsWith("/")) {
    throw new Error("Invalid backend request path");
  }
  await ensureBackend();
  const result = await authenticatedRequest(`${API_BASE_URL}${requestPath}`, { method, body });
  return result.payload;
}

function notifySessionExpired() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("auth:expired");
  }
}

function initializeAuthentication() {
  sessionStore = createSessionStore({
    safeStorage,
    files: fs.promises,
    tokenPath: path.join(app.getPath("userData"), "service-session.enc")
  });
  authenticatedRequest = createAuthenticatedRequester({
    fetchImpl: fetch,
    getToken: sessionStore.current,
    clearToken: sessionStore.clear,
    onExpired: notifySessionExpired
  });
  loginFlow = createLoginFlow({
    request: rawBackendRequest,
    openExternal: (url) => shell.openExternal(url),
    sessionStore
  });
  notificationFlow = createNotificationFlow({ request: requestBackend, openExternal: (url) => shell.openExternal(url) });
}

async function restoreSession() {
  const token = await sessionStore.restore();
  if (!token) return null;
  try {
    return await requestBackend({ requestPath: "/auth/session" });
  } catch {
    await sessionStore.clear();
    return null;
  }
}

async function logout() {
  try {
    if (sessionStore.current()) {
      await requestBackend({ method: "DELETE", requestPath: "/auth/session" });
    }
  } finally {
    await sessionStore.clear();
  }
}

function registerBackendHandlers() {
  ipcMain.handle("backend:request", (_event, request) => requestBackend(request));
  ipcMain.handle("backend:status", async () => {
    await ensureBackend();
    return { connected: true, baseUrl: API_BASE_URL };
  });
  ipcMain.handle("auth:restore", restoreSession);
  ipcMain.handle("auth:login", () => loginFlow.login());
  ipcMain.handle("auth:logout", logout);
  ipcMain.handle("notifications:connect", () => notificationFlow.connect());
  ipcMain.handle("notifications:status", () => notificationFlow.status());
  ipcMain.handle("notifications:disconnect", () => notificationFlow.disconnect());
}

function createWindow() {
  const window = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 920,
    minHeight: 680,
    backgroundColor: "#e8eeeb",
    title: "Stock Agent Demo",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });

  mainWindow = window;
  window.once("closed", () => { if (mainWindow === window) mainWindow = null; });
  window.loadFile(path.join(__dirname, "src", "index.html"));
}

app.whenReady().then(() => {
  initializeAuthentication();
  registerBackendHandlers();
  ensureBackend().catch((error) => console.error(error));
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
});
