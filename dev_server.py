"""PyCharm 本地调试启动入口。

默认启动管理端一体化服务：
    http://127.0.0.1:8000/admin

Debug 时不要开启 reload，否则断点容易被 uvicorn 子进程绕开。
"""
from __future__ import annotations

import os

import uvicorn


APP_TARGET = os.getenv("DEV_APP_TARGET", "app.api.import_app:app")
HOST = os.getenv("DEV_HOST", "127.0.0.1")
PORT = int(os.getenv("DEV_PORT", "8000"))


if __name__ == "__main__":
    uvicorn.run(
        APP_TARGET,
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info",
    )
