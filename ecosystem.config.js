const path = require("path");

const services = [
  { name: "nextcloud-db", service: "nextcloud-db" },
  { name: "nextcloud-app", service: "nextcloud" },
  { name: "nextcloud-nginx", service: "nginx" },
  { name: "rag-db", service: "rag-db" },
  { name: "rag-backend", service: "rag-api" },
  { name: "rag-frontend", service: "rag-ui" },
];

module.exports = {
  apps: services.map((s) => ({
    name: s.name,
    script: "./scripts/pm2-service-runner.js",
    args: s.service,
    cwd: __dirname,
    autorestart: true,
    watch: false,
    max_memory_restart: "300M",
    // Dedicated isolated log files per service for local monitoring
    out_file: path.join(__dirname, "logs", `${s.name}-out.log`),
    error_file: path.join(__dirname, "logs", `${s.name}-error.log`),
    log_date_format: "YYYY-MM-DD HH:mm:ss",
    merge_logs: true,
    env: {
      NODE_ENV: "production",
      SERVICE_NAME: s.name,
    },
  })),
};