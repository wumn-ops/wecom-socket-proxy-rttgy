"""wecom-socket-proxy-fkh 启动入口。"""

import uvicorn

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    print(f"wecom-socket-proxy-fkh 启动: http://{settings.host}:{settings.port}")
    print("模式: WebSocket 长连接（出站 wss://openws.work.weixin.qq.com）")
    print(f"HTTP 占位路径: {settings.wecom_callback_path}")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
