const { spawn, execSync } = require("child_process");
const path = require("path");

const service = process.argv[2];
if (!service) {
  console.error("Usage: node pm2-service-runner.js <service-name>");
  process.exit(1);
}

const repoDir = path.resolve(__dirname, "..");
const composeFile = path.join(repoDir, "deployment", "docker-compose.yml");
const envFile = path.join(repoDir, "deployment", ".env");

console.log(`[pm2:${service}] Ensuring network and volumes are initialized...`);
try {
  // Ensure network and volumes exist before starting individual service
  execSync(`docker compose -f "${composeFile}" --env-file "${envFile}" up --no-start ${service}`, {
    stdio: "ignore",
    cwd: repoDir,
  });
} catch (e) {
  // Ignore
}

console.log(`[pm2:${service}] Starting container: ${service}...`);
try {
  execSync(`docker compose -f "${composeFile}" --env-file "${envFile}" up -d ${service}`, {
    stdio: "inherit",
    cwd: repoDir,
  });
  console.log(`[pm2:${service}] Container started.`);
} catch (err) {
  console.error(`[pm2:${service}] Start error:`, err.message);
}

// Stream logs of this specific service into PM2 stdout/stderr
const logStream = spawn("docker", [
  "compose",
  "-f", composeFile,
  "--env-file", envFile,
  "logs",
  "-f",
  "--no-log-prefix",
  service
], { cwd: repoDir, stdio: "inherit" });

function cleanup() {
  console.log(`\n[pm2:${service}] Stopping container...`);
  if (logStream) {
    try { logStream.kill(); } catch (e) {}
  }
  try {
    execSync(`docker compose -f "${composeFile}" stop ${service}`, {
      stdio: "inherit",
      cwd: repoDir,
    });
    console.log(`[pm2:${service}] Container stopped.`);
  } catch (err) {
    // Ignore error on stop
  }
  process.exit(0);
}

process.on("SIGINT", cleanup);
process.on("SIGTERM", cleanup);
process.on("exit", () => {
  if (logStream) {
    try { logStream.kill(); } catch (e) {}
  }
});