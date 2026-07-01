const { app, BrowserWindow, ipcMain, shell } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const API_BASE_URL = process.env.STOCK_AGENT_API_URL || "http://127.0.0.1:8000";
const repositoryRoot = path.resolve(__dirname, "..");
let backendProcess = null;

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

async function requestBackend({ method = "GET", requestPath, body }) {
  if (typeof requestPath !== "string" || !requestPath.startsWith("/")) {
    throw new Error("Invalid backend request path");
  }
  await ensureBackend();
  const response = await fetch(`${API_BASE_URL}${requestPath}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(120000)
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail = typeof payload?.detail === "string" ? payload.detail : JSON.stringify(payload?.detail || payload);
    throw new Error(detail || `Backend request failed (${response.status})`);
  }
  return payload;
}

function registerBackendHandlers() {
  ipcMain.handle("backend:request", (_event, request) => requestBackend(request));
  ipcMain.handle("backend:status", async () => {
    await ensureBackend();
    return { connected: true, baseUrl: API_BASE_URL };
  });
  ipcMain.handle("backend:kakao-login", async () => {
    await ensureBackend();
    await shell.openExternal(`${API_BASE_URL}/auth/kakao/login`);
  });
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

  window.loadFile(path.join(__dirname, "src", "index.html"));
}

app.whenReady().then(() => {
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
