#!/usr/bin/env python3
"""Mac/Windows 桌面去水印工具 - 虾王开发
功能：
1. 拖拽图片到窗口 → 自动去右下角水印 → 保存到原图同目录
2. 或点按钮选图（兼容老用户）
3. 批量拖拽多张图
"""
import os
import sys
import platform
import traceback
from tkinter import Tk, Label, Button, Frame, Text, END
from tkinter import filedialog, messagebox
from PIL import Image, ImageDraw, ImageFilter

# 拖拽库（py2app 打包需要包含）
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False

def remove_watermark(input_path, output_path=None):
    """去右下角水印（豆包 AI / 类似平台）"""
    if output_path is None:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_去水印{ext}"
    img = Image.open(input_path).convert("RGB")
    w, h = img.size
    # 自适应水印区域（右下角 ~260×60）
    margin_r = max(20, int(w * 0.02))
    margin_b = max(20, int(h * 0.02))
    wm_w = min(320, w // 4)
    wm_h = min(80, h // 20)
    wm_x0 = w - margin_r - wm_w
    wm_y0 = h - margin_b - wm_h
    wm_x1 = w - margin_r
    wm_y1 = h - margin_b
    draw = ImageDraw.Draw(img)
    sample_y = max(0, wm_y0 - 40)
    samples = [img.getpixel((dx, sample_y)) for dx in range(wm_x0, wm_x1, 10)]
    avg_color = tuple(sum(c[i] for c in samples) // len(samples) for i in range(3))
    draw.rectangle([wm_x0, wm_y0, wm_x1, wm_y1], fill=avg_color)
    pad = 20
    crop = img.crop((max(0, wm_x0 - pad), max(0, wm_y0 - pad), min(w, wm_x1 + pad), min(h, wm_y1 + pad)))
    crop_blur = crop.filter(ImageFilter.GaussianBlur(radius=8))
    img.paste(crop_blur, (max(0, wm_x0 - pad), max(0, wm_y0 - pad)))
    img.save(output_path, quality=92)
    return output_path

class WatermarkRemoverApp:
    def __init__(self):
        if HAS_DND:
            self.root = TkinterDnD.Tk()
        else:
            self.root = Tk()
        self.root.title(f"去水印 · 虾王")
        self.root.geometry("480x360")
        self.root.resizable(False, False)

        # 标题
        Label(self.root, text="🦞 桌面去水印工具",
              font=("Helvetica", 18, "bold")).pack(pady=12)
        Label(self.root, text="拖入图片自动去右下角水印 · 支持批量",
              font=("Helvetica", 10)).pack(pady=2)

        # 拖拽区域
        if HAS_DND:
            drop_frame = Frame(self.root, bg="#f0f0f0", relief="ridge", bd=2)
            drop_frame.pack(pady=10, padx=20, fill="both", expand=True)
            drop_label = Label(drop_frame, text="📥 拖拽图片到这里\n（支持多张）",
                              font=("Helvetica", 14), bg="#f0f0f0", fg="#666")
            drop_label.pack(expand=True)
            drop_label.drop_target_register(DND_FILES)
            drop_label.dnd_bind("<<Drop>>", self.on_drop)
            self.drop_label = drop_label
        else:
            Label(self.root, text="⚠️ 拖拽库未安装，请用按钮选图",
                  font=("Helvetica", 10), fg="orange").pack(pady=10)

        # 按钮
        btn_frame = Frame(self.root)
        btn_frame.pack(pady=8)
        Button(btn_frame, text="📷 选图处理",
               command=self.select_files, width=14, height=2).pack(side="left", padx=6)
        Button(btn_frame, text="📚 批量选图",
               command=self.select_files_batch, width=14, height=2).pack(side="left", padx=6)

        # 日志区
        self.log = Text(self.root, height=6, font=("Menlo", 9))
        self.log.pack(pady=8, padx=20, fill="x")

        Label(self.root, text=f"虾王开发 · {platform.system()}",
              font=("Helvetica", 8), fg="gray").pack(side="bottom", pady=4)

    def log_msg(self, msg):
        self.log.insert(END, msg + "\n")
        self.log.see(END)
        self.root.update()

    def on_drop(self, event):
        """拖拽事件处理"""
        files = self.root.tk.splitlist(event.data)
        self.process_files(files)

    def select_files(self):
        files = filedialog.askopenfilenames(
            title="选择要去水印的图片",
            filetypes=[("图片文件", "*.jpg *.jpeg *.png *.webp *.bmp"), ("所有文件", "*.*")]
        )
        if files:
            self.process_files(files)

    def select_files_batch(self):
        files = filedialog.askopenfilenames(
            title="批量选择（按住 Cmd/Ctrl 多选）",
            filetypes=[("图片文件", "*.jpg *.jpeg *.png *.webp *.bmp"), ("所有文件", "*.*")]
        )
        if files:
            self.process_files(files)

    def process_files(self, files):
        ok, fail = [], []
        for f in files:
            if not os.path.exists(f):
                fail.append(f"{os.path.basename(f)}: 文件不存在")
                continue
            try:
                out = remove_watermark(f)
                ok.append(out)
                self.log_msg(f"✅ {os.path.basename(out)}")
            except Exception as e:
                fail.append(f"{os.path.basename(f)}: {e}")
                self.log_msg(f"❌ {os.path.basename(f)}: {e}")
        summary = f"完成：{len(ok)} 张成功"
        if fail:
            summary += f"，{len(fail)} 张失败"
        self.log_msg(summary)
        if ok:
            messagebox.showinfo("完成", f"已处理 {len(ok)} 张图片\n保存到原图同目录（加 _去水印 后缀）")

if __name__ == "__main__":
    try:
        app = WatermarkRemoverApp()
        app.root.mainloop()
    except Exception as e:
        # 打包后无 console 时弹错误窗
        if platform.system() == "Darwin" and getattr(sys, "frozen", False):
            messagebox.showerror("错误", f"启动失败：\n{e}")
        else:
            traceback.print_exc()
