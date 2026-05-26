# wecom-socket-proxy-fkh

`wecom-socket-proxy` 的**独立副本**，用于单独部署一个 WebSocket 长连接实例，实现 FKH 相关定制功能，**不影响** `wecom-socket-proxy` / `wecom-proxy` 等其它项目。

## 与 wecom-socket-proxy 的关系

| 项 | wecom-socket-proxy | wecom-socket-proxy-fkh（本项目） |
|---|---|---|
| 代码 | 同源 | 完整复制，可独立演进 |
| 默认端口 | 8000 | **8001** |
| Bot 凭证 | 原机器人 | **须配置独立 BotID + Secret** |
| 状态文件 | `data/launch_notified.json` | 各自独立目录 |
| systemd | `wecom-socket-proxy.service` | `wecom-socket-proxy-fkh.service` |

> 同一机器人 API 模式只能二选一（Webhook 或长连接）。本实例须使用**独立测试机器人**，并与原实例**同时运行**（不同端口 + 不同 Nginx 反代）。

## 快速开始

```powershell
cd D:\aiworkspace\cursor_space\wecom-socket-proxy-fkh
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# 编辑 .env：填入独立 WECOM_BOT_ID、WECOM_BOT_SECRET、PUBLIC_BASE_URL 等
python run.py
```

启动后访问：`http://127.0.0.1:8001/health`

## 企微后台配置

1. 创建/选择**独立**智能机器人 → API 模式 → **长连接**
2. 复制 **BotID**、**Secret** 到本项目的 `.env`
3. 保存后启动本服务；日志应出现 `WebSocket 认证成功`

## HTTP 接口

与 `wecom-socket-proxy` 相同：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 服务信息 |
| GET | `/health` | 健康检查 + WebSocket 连接状态 |
| GET/POST | `/wecom/aibot/callback` | Webhook 占位 |
| POST | `/api/test/push?chat_id=` | 测试主动推送 |
| GET | `/register/upload` | H5 图片上传页 |
| GET/POST | `/register/upload/api/*` | 上传 API |
| GET | `/feedback` | H5 测试评价页 |
| GET/POST | `/feedback/api/*` | 评价 API |

## 服务器并行部署

```bash
# Nginx 新增 upstream 指向 127.0.0.1:8001（或使用独立域名）
sudo cp deploy/wecom-socket-proxy-fkh.service /etc/systemd/system/
# 修改 service 内 WorkingDirectory / ExecStart 路径
sudo systemctl daemon-reload
sudo systemctl enable --now wecom-socket-proxy-fkh
curl http://127.0.0.1:8001/health
```

## 功能说明

需求登记、上线测试提醒、H5 评价等流程与 `wecom-socket-proxy` 一致，详见原项目 README。后续 FKH 定制功能在本仓库独立开发即可。
