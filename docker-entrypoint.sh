#!/bin/sh
# FileCodeBox 容器入口：兼容式非 root 降权。
#
# 默认以 root 进入（兼容存量 root 属主的数据卷），按需修正 data 目录属主后
# 用 gosu 降权到 app 用户运行；若部署方显式指定了 user（非 root），则直接运行
# 不做任何 chown，保证两种形态都可预期。
set -e

DATA_DIR="${DATA_DIR:-/app/data}"

if [ "$(id -u)" = "0" ]; then
    mkdir -p "$DATA_DIR"
    # 仅当存在非 app 属主的文件时才 chown，避免大卷启动变慢
    if [ -n "$(find "$DATA_DIR" ! -uid "$(id -u app)" -print -quit 2>/dev/null)" ]; then
        chown -R app:app "$DATA_DIR"
    fi
    exec gosu app "$@"
fi

exec "$@"
