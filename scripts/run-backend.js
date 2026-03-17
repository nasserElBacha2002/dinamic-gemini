#!/usr/bin/env node
/**
 * Start the backend API server (uvicorn). Run from repo root.
 * Expects backend to be installed: pip install -e backend/
 */
const path = require("path");
const { spawn } = require("child_process");

const root = path.resolve(__dirname, "..");
const backendDir = path.join(root, "backend");
const isWin = process.platform === "win32";
const binDir = isWin ? "Scripts" : "bin";
const pyName = isWin ? "python.exe" : "python";
// Prefer backend/.venv (has backend deps); fallback to root .venv
const py = require("fs").existsSync(path.join(backendDir, ".venv", binDir, pyName))
  ? path.join(backendDir, ".venv", binDir, pyName)
  : path.join(root, ".venv", binDir, pyName);
const port = process.env.PORT || "8000";

const env = { ...process.env, PYTHONPATH: backendDir };
const child = spawn(py, ["-m", "uvicorn", "src.api.server:app", "--reload", "--port", port], {
  cwd: backendDir,
  env,
  stdio: "inherit",
  shell: false,
});

child.on("error", (err) => {
  console.error("[run-backend] Failed to start:", err.message);
  console.error("Ensure .venv exists and backend is installed: pip install -e backend/");
  process.exit(1);
});
child.on("exit", (code) => process.exit(code != null ? code : 0));
