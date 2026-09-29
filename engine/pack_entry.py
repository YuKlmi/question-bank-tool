# -*- coding: utf-8 -*-
"""PyInstaller 打包入口。

打包时必须用绝对导入（相对导入在独立脚本里跑不起来）：
    pyinstaller --onefile --name qtb-engine ^
      --paths . ^
      --add-data "engine/templates;engine/templates" ^
      --hidden-import win32com.client --hidden-import pythoncom ^
      --distpath engine/dist ^
      engine/pack_entry.py
"""
from __future__ import annotations

import sys

from engine.rpc import main

if __name__ == "__main__":
    sys.exit(main())
