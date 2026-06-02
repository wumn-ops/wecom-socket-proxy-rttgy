# wecom-socket-proxy-rttgy

`wecom-socket-proxy` 的**独立副本**，用于单独部署 RTTGY 实例，**不影响**其它项目。

## 与 wecom-socket-proxy 的区别

| 项 | wecom-socket-proxy | wecom-socket-proxy-rttgy |
|---|---|---|
| 后端端口 | 8000 | **8001**（部署时需与 fkh 等实例错开） |
| Nginx 路径 | `/health`、`/register/upload` 等 | **带 `/rttgy` 后缀** |
| Bot 凭证 | 原机器人 | **独立 BotID + Secret** |

## 公网访问路径（Nginx → 后端端口）

与现有 `wecom.vazyme.com:8021` 共用域名，通过路径区分：

| 用途 | 公网 URL |
|------|----------|
| 健康检查 | `https://wecom.vazyme.com:8021/health/rttgy` |
| Webhook 占位 | `https://wecom.vazyme.com:8021/wecom/aibot/callback/rttgy` |
| H5 上传页 | `https://wecom.vazyme.com:8021/register/upload/rttgy?token=...` |
| H5 评价页 | `https://wecom.vazyme.com:8021/feedback/rttgy?token=...` |

卡片内 H5 链接由 `PUBLIC_BASE_URL` + `REGISTER_UPLOAD_PATH` / `FEEDBACK_PATH` 自动生成。

## Nginx 配置示例

见 `deploy/nginx-rttgy.conf`：

```nginx
location /wecom/aibot/callback/rttgy {
    proxy_pass http://192.168.140.92:8001;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
location /health/rttgy {
    proxy_pass http://192.168.140.92:8001;
}
location /register/upload/rttgy {
    proxy_pass http://192.168.140.92:8001;
    client_max_body_size 10m;
}
location /feedback/rttgy {
    proxy_pass http://192.168.140.92:8001;
}
```

> `location /register/upload/rttgy` 为前缀匹配，会同时覆盖 `/register/upload/rttgy/api/*` 等子路径。

## 快速开始

```powershell
cd D:\aiworkspace\cursor_space\wecom-socket-proxy-rttgy
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# 编辑 .env：独立 Bot 凭证、智能表格、独立 PORT 等
python run.py
```

本地直连：`http://127.0.0.1:8001/health/rttgy`

## 关键 .env 配置

```env
PORT=8001
WECOM_CALLBACK_PATH=/wecom/aibot/callback/rttgy
HEALTH_PATH=/health/rttgy
PUBLIC_BASE_URL=https://wecom.vazyme.com:8021
REGISTER_UPLOAD_PATH=/register/upload/rttgy
FEEDBACK_PATH=/feedback/rttgy
```
