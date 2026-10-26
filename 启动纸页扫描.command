#!/bin/zsh
cd "${0:A:h}"
if [[ -d "dist/纸页扫描.app" ]]; then
    open "dist/纸页扫描.app"
elif [[ -x ".venv/bin/python" ]]; then
    exec .venv/bin/python main.py
else
    print "未找到运行环境。请打开 dist 中的纸页扫描.app，或按 README 安装开发环境。"
    read "?按回车关闭窗口"
fi
