#!/usr/bin/env node
/**
 * Start the backend API server (uvicorn). Run from repo root.
 * Expects backend to be installed: pip install -e backend/
 */
const path = require("path");
const { spawn } = require("child_process");

const root = path.resolve(__dirname, "..");
const isWin = process.platform === "win32";
const py = path.join(root, ".venv", isWin ? "Scripts" : "bin", isWin ? "python.exe" : "python");
const port = process.env.PORT || "8000";

const child = spawn(py, ["-m", "uvicorn", "src.api.server:app", "--reload", "--port", port], {
  cwd: root,
  stdio: "inherit",
  shell: false,
});

child.on("error", (err) => {
  console.error("[run-backend] Failed to start:", err.message);
  console.error("Ensure .venv exists and backend is installed: pip install -e backend/");
  process.exit(1);
});
child.on("exit", (code) => process.exit(code != null ? code : 0));
