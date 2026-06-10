"""wecom-socket-proxy-rttgy 启动入口。"""

import uvicorn

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("警告: 未安装 Pillow，加密图片解密后无法自动压缩。")
        print("请在本项目虚拟环境中执行:")
        print("  .venv\\Scripts\\python.exe -m pip install -r requirements.txt")
        print("（勿直接使用 pip install，可能装到其他项目的 venv）")
    print(f"wecom-socket-proxy-rttgy 启动: http://{settings.host}:{settings.port}")
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
