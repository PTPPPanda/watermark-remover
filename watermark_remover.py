"""
Watermark Remover v2 - 升级版
- 自动检测水印（无需手动框选）
- 拉边 Inpaint 算法（智能填充，不再色块）
- 拖拽图片到窗口即可处理
- 跨平台 Mac/Win
"""
import sys
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageDraw, ImageFilter
import numpy as np
import io
import json

# 拖拽支持
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False


def detect_watermark_region(img, region_hint='bottom-right'):
    """
    自动检测水印区域
    返回 (x1, y1, x2, y2)
    策略: 在指定区域找文字（高对比度 + 接近背景色的文字颜色）
    """
    w, h = img.size
    arr = np.array(img.convert('RGBA'))
    h_a, w_a = arr.shape[:2]

    # 默认扫描右下角 25% 区域
    if region_hint == 'bottom-right':
        scan_x1 = int(w_a * 0.65)
        scan_y1 = int(h_a * 0.80)
        scan_x2 = w_a
        scan_y2 = h_a
    elif region_hint == 'bottom-left':
        scan_x1 = 0
        scan_y1 = int(h_a * 0.80)
        scan_x2 = int(w_a * 0.35)
        scan_y2 = h_a
    elif region_hint == 'top-right':
        scan_x1 = int(w_a * 0.65)
        scan_y1 = 0
        scan_x2 = w_a
        scan_y2 = int(h_a * 0.20)
    elif region_hint == 'top-left':
        scan_x1 = 0
        scan_y1 = 0
        scan_x2 = int(w_a * 0.35)
        scan_y2 = int(h_a * 0.20)
    else:
        scan_x1 = 0
        scan_y1 = 0
        scan_x2 = w_a
        scan_y2 = h_a

    sub = arr[scan_y1:scan_y2, scan_x1:scan_x2]
    if sub.size == 0:
        return None

    # 转灰度
    if sub.shape[2] == 4:
        # 含 alpha
        rgb = sub[:, :, :3]
        alpha = sub[:, :, 3]
        # 只看非透明区域
        mask_visible = alpha > 128
    else:
        rgb = sub
        mask_visible = np.ones(sub.shape[:2], dtype=bool)

    gray = np.dot(rgb[..., :3], [0.299, 0.587, 0.114])

    # 计算背景色（最频繁像素）
    visible_pixels = gray[mask_visible]
    if len(visible_pixels) == 0:
        return None
    bg_color = int(np.median(visible_pixels))

    # 找和背景差异 > 阈值 的像素（文字/水印）
    diff = np.abs(gray.astype(int) - bg_color)
    text_mask = (diff > 30) & mask_visible

    if text_mask.sum() < 50:
        return None

    # 找 bbox
    ys, xs = np.where(text_mask)
    x1 = int(xs.min()) + scan_x1
    y1 = int(ys.min()) + scan_y1
    x2 = int(xs.max()) + scan_x1
    y2 = int(ys.max()) + scan_y1

    # 扩展 10px 边距
    pad = 10
    x1 = max(0, x1 - pad)
    y1 = max(0, y1 - pad)
    x2 = min(w_a, x2 + pad)
    y2 = min(h_a, y2 + pad)

    return (x1, y1, x2, y2)


def inpaint_region(img, region, iterations=3):
    """
    Inpaint 算法：拿周围背景智能填充水印区域
    实现: 多次拉边 + 模糊扩散
    """
    if region is None:
        return img

    x1, y1, x2, y2 = region
    w, h = img.size
    result = img.copy().convert('RGBA')
    arr = np.array(result)

    # 1. 取水印周围背景样本
    pad_sample = 30
    sx1 = max(0, x1 - pad_sample)
    sy1 = max(0, y1 - pad_sample)
    sx2 = min(w, x2 + pad_sample)
    sy2 = min(h, y2 + pad_sample)

    # 2. 多次模糊 + 拉边（从外向内）
    region_w = x2 - x1
    region_h = y2 - y1

    # 用 PIL 的 inpaint-like 操作: 多次 GaussianBlur + 取边缘像素填充
    work = result.copy()

    for i in range(iterations):
        # 模糊整个图
        blurred = work.filter(ImageFilter.GaussianBlur(radius=3 + i * 2))

        # 替换水印区域
        blurred_arr = np.array(blurred)
        work_arr = np.array(work)

        # 拉边: 从水印区边缘向内做 alpha blend
        edge_mask = np.zeros((h, w), dtype=np.float32)

        # 创建渐变 mask: 中心 1, 边缘 0
        for yy in range(y1, y2):
            for xx in range(x1, x2):
                # 距边界的归一化距离
                dx = min(xx - x1, x2 - 1 - xx) / max(1, region_w / 2)
                dy = min(yy - y1, y2 - 1 - yy) / max(1, region_h / 2)
                d = min(dx, dy)
                edge_mask[yy, xx] = min(1.0, d * 2)

        # 3 通道 mask
        edge_mask_3 = edge_mask[..., None]

        # 原图 + 模糊图 blend
        work_arr_float = work_arr.astype(np.float32)
        blurred_arr_float = blurred_arr.astype(np.float32)

        blended = work_arr_float * (1 - edge_mask_3) + blurred_arr_float * edge_mask_3
        work = Image.fromarray(blended.astype(np.uint8), 'RGBA')

    return work


def remove_watermark_smart(img, region_hint='bottom-right'):
    """
    智能去水印主函数
    1. 自动检测水印位置
    2. Inpaint 智能填充
    """
    # 1. 检测
    region = detect_watermark_region(img, region_hint)
    if region is None:
        return img, None

    # 2. Inpaint
    result = inpaint_region(img, region)

    return result, region


# ====== GUI ======

class WatermarkRemoverApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Watermark Remover 虾王 v2")
        self.root.geometry("800x600")

        self.current_image = None
        self.current_path = None
        self.processed_image = None
        self.region_hint = tk.StringVar(value='bottom-right')

        self._build_ui()

    def _build_ui(self):
        # 顶部工具栏
        toolbar = tk.Frame(self.root)
        toolbar.pack(fill=tk.X, padx=8, pady=8)

        tk.Button(toolbar, text="📂 打开图片", command=self.open_image).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="💾 保存", command=self.save_image).pack(side=tk.LEFT, padx=2)

        tk.Label(toolbar, text="  水印位置:").pack(side=tk.LEFT, padx=(20, 4))
        for label, val in [("右下", "bottom-right"), ("左下", "bottom-left"),
                           ("右上", "top-right"), ("左上", "top-left"),
                           ("全图扫描", "all")]:
            tk.Radiobutton(toolbar, text=label, variable=self.region_hint,
                          value=val).pack(side=tk.LEFT, padx=2)

        tk.Button(toolbar, text="🚀 去水印", command=self.process,
                  bg='#4CAF50', fg='white', font=('Arial', 11, 'bold')).pack(side=tk.RIGHT, padx=4)

        # 拖拽区域
        self.drop_frame = tk.Frame(self.root, bg='#f0f0f0', relief=tk.RIDGE, bd=2)
        self.drop_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.drop_label = tk.Label(
            self.drop_frame,
            text="🖼️  拖拽图片到这里\n或点 '📂 打开图片'",
            bg='#f0f0f0', fg='#666',
            font=('Arial', 16))
        self.drop_label.pack(expand=True)

        # 状态栏
        self.status = tk.Label(self.root, text="就绪 · 智能去水印 v2", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        # 拖拽支持
        if HAS_DND:
            self.drop_frame.drop_target_register(DND_FILES)
            self.drop_frame.dnd_bind('<<Drop>>', self.on_drop)
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind('<<Drop>>', self.on_drop)
        else:
            self.drop_label.config(text="⚠️ tkinterdnd2 未装\n点 '📂 打开图片' 选文件\n\npip install tkinterdnd2")

    def on_drop(self, event):
        path = event.data
        if path.startswith('{'):
            path = path[1:-1]
        if os.path.isfile(path):
            self.load_image(path)

    def open_image(self):
        path = filedialog.askopenfilename(
            title="选择图片",
            filetypes=[("图片", "*.jpg *.jpeg *.png *.bmp *.webp"), ("所有", "*.*")]
        )
        if path:
            self.load_image(path)

    def load_image(self, path):
        try:
            self.current_image = Image.open(path).convert('RGBA')
            self.current_path = path
            self.processed_image = None
            self._show_image(self.current_image)
            self.status.config(text=f"已加载: {os.path.basename(path)} ({self.current_image.size[0]}x{self.current_image.size[1]})")
        except Exception as e:
            messagebox.showerror("错误", f"打开失败: {e}")

    def _show_image(self, img):
        # 缩放到窗口大小
        max_size = (700, 500)
        img_copy = img.copy()
        img_copy.thumbnail(max_size, Image.Resampling.LANCZOS)

        # 存到 BytesIO 给 tkinter
        from PIL import ImageTk
        photo = ImageTk.PhotoImage(img_copy)

        # 替换 drop_label 为 canvas
        for widget in self.drop_frame.winfo_children():
            widget.destroy()

        canvas = tk.Canvas(self.drop_frame, bg='#f0f0f0', highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        canvas.create_image(canvas.winfo_reqwidth() // 2, canvas.winfo_reqheight() // 2,
                           image=photo, anchor=tk.CENTER)
        canvas.image = photo  # 防止 GC

    def process(self):
        if not self.current_image:
            messagebox.showwarning("提示", "先加载图片")
            return
        self.status.config(text="🔄 正在去水印...")
        self.root.update()

        try:
            result, region = remove_watermark_smart(self.current_image, self.region_hint.get())
            self.processed_image = result
            if region:
                self.status.config(text=f"✅ 完成 · 检测到水印区域: {region}")
            else:
                self.status.config(text="⚠️ 未检测到水印，请换个扫描位置")
            self._show_image(result)
        except Exception as e:
            messagebox.showerror("错误", f"处理失败: {e}")
            self.status.config(text="❌ 失败")

    def save_image(self):
        if not self.processed_image:
            messagebox.showwarning("提示", "先处理图片")
            return
        out = filedialog.asksaveasfilename(
            title="保存",
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg"), ("WebP", "*.webp")]
        )
        if out:
            try:
                # 去掉 alpha 通道如果存 jpg
                img = self.processed_image
                if out.lower().endswith(('.jpg', '.jpeg')) and img.mode == 'RGBA':
                    bg = Image.new('RGB', img.size, (255, 255, 255))
                    bg.paste(img, mask=img.split()[3])
                    img = bg
                img.save(out)
                self.status.config(text=f"✅ 已保存: {out}")
            except Exception as e:
                messagebox.showerror("错误", f"保存失败: {e}")


def main():
    if HAS_DND:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()

    app = WatermarkRemoverApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
