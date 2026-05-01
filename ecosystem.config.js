const HOME = process.env.HOME;
const PROJECT = `${HOME}/Documents/Build-Factory`;
const VENV = `${PROJECT}/.venv`;
const NODE = `${HOME}/.nvm/versions/node/v22.21.1/bin/node`;
const NEXT = `${PROJECT}/frontend/node_modules/.bin/next`;

// .env ファイルを読み込んで環境変数として展開する
const fs = require('fs');
const path = require('path');
function loadEnv(envPath) {
  try {
    const content = fs.readFileSync(envPath, 'utf8');
    const env = {};
    content.split('\n').forEach(line => {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) return;
      const idx = trimmed.indexOf('=');
      if (idx === -1) return;
      const key = trimmed.slice(0, idx).trim();
      const val = trimmed.slice(idx + 1).trim();
      env[key] = val;
    });
    return env;
  } catch (e) {
    return {};
  }
}
const dotenv = loadEnv(path.join(PROJECT, '.env'));

module.exports = {
  apps: [
    {
      name: "bf-fastapi",
      cwd: `${PROJECT}/backend`,
      script: `${VENV}/bin/uvicorn`,
      args: "main:app --host 0.0.0.0 --port 8001",
      interpreter: "none",
      env: {
        PATH: `${VENV}/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin`,
        PYTHONPATH: `${PROJECT}/backend`,
        ...dotenv,
      },
      error_file: `${HOME}/.pm2/logs/bf-fastapi-error.log`,
      out_file:   `${HOME}/.pm2/logs/bf-fastapi-out.log`,
      watch: false,
      autorestart: true,
      max_restarts: 5,
      restart_delay: 3000,
    },
    {
      name: "bf-nextjs",
      cwd: `${PROJECT}/frontend`,
      script: NEXT,
      args: "dev -p 3001",
      interpreter: "/bin/sh",
      env: {
        PATH: `${HOME}/.nvm/versions/node/v22.21.1/bin:/usr/local/bin:/usr/bin:/bin`,
        NODE_ENV: "development",
      },
      error_file: `${HOME}/.pm2/logs/bf-nextjs-error.log`,
      out_file:   `${HOME}/.pm2/logs/bf-nextjs-out.log`,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 3000,
    },
    // cloudflared は T9-02（Chatwork設定後）に追加
    // { name: "cloudflared", script: "cloudflared", args: "tunnel run engine-base", ... }
  ],
};
