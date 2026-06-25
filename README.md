# 🦞 WatermarkRemover 虾王版

桌面去水印工具 · 拖拽图片 · 自动去右下角水印（豆包 AI / 类似平台）

## 功能

- 拖拽图片到窗口（或点按钮选图）
- 自动去除右下角水印（采样背景色 + 高斯模糊）
- 输出到原图同目录（加 `_去水印` 后缀）
- 单张 / 批量处理
- 支持 JPG / PNG / WebP / BMP

## 启动方式

### Windows（推荐 .exe 方式）

下载 [Releases](https://github.com/PTPPPanda/watermark-remover/releases) 里最新的 `WatermarkRemover.exe`，双击即可。

### 自己打包 Windows .exe

```cmd
:: 安装 Python 3.9+ （勾选 Add to PATH）
pip install pillow tkinterdnd2 pyinstaller
pyinstaller --onefile --noconsole --name WatermarkRemover watermark_remover.py
```

或直接双击 `build_windows.bat`。

### Mac

```bash
pip3 install pillow tkinterdnd2
python3 watermark_remover.py
```

## License

虾王开发 · 内部使用
