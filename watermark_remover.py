"""
Watermark Remover v3 - 修复版
- 改进检测：更灵活的对比度阈值
- 改进填充：单次强模糊 + 羽化边缘（不再迭代整图模糊）
- 向量化 numpy 操作（不再 O(w*h) Python 循环）
"""
import sys
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageDraw, ImageFilter
import numpy as np
import io
import json

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False


def detect_watermark_region(img, region_hint='bottom-right', sensitivity=25):
    """
    自动检测水印区域。
    sensitivity: 对比度阈值，越低越敏感（默认 25，范围 10-60）
    返回 (x1, y1, x2, y2) 或 None
    """
    w, h = img.size
    arr = np.array(img.convert('RGBA'))
    h_a, w_a = arr.shape[:2]

    # 扫描区域映射
    zones = {
        'bottom-right': (0.65, 0.80, 1.0, 1.0),
        'bottom-left':  (0, 0.80, 0.35, 1.0),
        'top-right':    (0.65, 0, 1.0, 0.20),
        'top-left':     (0, 0, 0.35, 0.20),
        'all':          (0, 0, 1.0, 1.0),
    }
    z = zones.get(region_hint, zones['all'])
    scan_x1 = int(w_a * z[0])
    scan_y1 = int(h_a * z[1])
    scan_x2 = int(w_a * z[2])
    scan_y2 = int(h_a * z[3])

    sub = arr[scan_y1:scan_y2, scan_x1:scan_x2]
    if sub.size == 0:
        return None

    # RGB + alpha
    if sub.shape[2] == 4:
        rgb = sub[:, :, :3]
        alpha = sub[:, :, 3]
        mask_visible = alpha > 100
    else:
        rgb = sub
        mask_visible = np.ones(sub.shape[:2], dtype=bool)

    gray = np.dot(rgb[..., :3], [0.299, 0.587, 0.114])
    visible_pixels = gray[mask_visible]
    if len(visible_pixels) < 100:
        return None

    # 背景色 = 中位数
    bg_color = float(np.median(visible_pixels))

    # 找差异像素
    diff = np.abs(gray.astype(float) - bg_color)
    text_mask = (diff > sensitivity) & mask_visible

    if text_mask.sum() < 30:
        return None

    ys, xs = np.where(text_mask)
    x1 = int(xs.min()) + scan_x1
    y1 = int(ys.min()) + scan_y1
    x2 = int(xs.max()) + scan_x1 + 1
    y2 = int(ys.max()) + scan_y1 + 1

    # 扩展边距
    pad = 15
    x1 = max(0, x1 - pad)
    y1 = max(0, y1 - pad)
    x2 = min(w_a, x2 + pad)
    y2 = min(h_a, y2 + pad)

    return (x1, y1, x2, y2)


def inpaint_region(img, region, blur_radius=18, feather=12):
    """
    改进版填充：
    1. 单次强模糊（不再迭代整图）
    2. 羽化边缘（用 GaussianBlur mask）
    3. 全 numpy 向量化
    """
    if region is None:
        return img

    x1, y1, x2, y2 = region
    result = img.copy().convert('RGBA')
    arr = np.array(result).astype(np.float32)
    h, w = arr.shape[:2]

    # -- mask：水印区 = 1，其余 = 0 --
    mask = np.zeros((h, w), dtype=np.float32)
    mask[y1:y2, x1:x2] = 1.0

    # 羽化 mask（Gaussian blur mask 使边缘渐变）
    mask_u8 = (mask * 255).astype(np.uint8)
    mask_blurred = Image.fromarray(mask_u8).filter(
        ImageFilter.GaussianBlur(radius=feather)
    )
    mask_arr = np.array(mask_blurred).astype(np.float32) / 255.0
    mask_4 = np.stack([mask_arr] * 4, axis=-1)

    # -- 强模糊整图，但只在水印区生效 --
    blurred = result.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    blurred_arr = np.array(blurred).astype(np.float32)

    # blend: mask=1 → 全用模糊 / mask=0 → 保留原图
    blended = arr * (1.0 - mask_4) + blurred_arr * mask_4

    return Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8), 'RGBA')


def remove_watermark_smart(img, region_hint='bottom-right', sensitivity=25):
    region = detect_watermark_region(img, region_hint, sensitivity)
    if region is None:
        return img, None
    result = inpaint_region(img, region)
    return result, region


# ====== GUI ======

class WatermarkRemoverApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Watermark Remover 虾王 v3")
        self.root.geometry("900x650")

        self.current_image = None
        self.current_path = None
        self.processed_image = None
        self.region_hint = tk.StringVar(value='bottom-right')
        self.sensitivity = tk.IntVar(value=25)

        self._build_ui()

    def _build_ui(self):
        toolbar = tk.Frame(self.root)
        toolbar.pack(fill=tk.X, padx=8, pady=8)

        tk.Button(toolbar, text="📂 打开", command=self.open_image, width=8).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="💾 保存", command=self.save_image, width=8).pack(side=tk.LEFT, padx=2)

        # 位置选择
        tk.Label(toolbar, text="  位置:").pack(side=tk.LEFT, padx=(20, 2))
        for label, val in [
            ("右下", "bottom-right"), ("左下", "bottom-left"),
            ("右上", "top-right"), ("左上", "top-left"), ("全图", "all")
        ]:
            tk.Radiobutton(toolbar, text=label, variable=self.region_hint,
                          value=val).pack(side=tk.LEFT, padx=1)

        # 灵敏度滑块
        tk.Label(toolbar, text="  灵敏度:").pack(side=tk.LEFT, padx=(15, 2))
        tk.Scale(toolbar, from_=10, to=60, orient=tk.HORIZONTAL,
                 variable=self.sensitivity, length=120).pack(side=tk.LEFT)
        self.sens_label = tk.Label(toolbar, text="25", width=3)
        self.sens_label.pack(side=tk.LEFT)
        self.sensitivity.trace_add('write', lambda *a: self.sens_label.config(
            text=str(self.sensitivity.get())))

        tk.Button(toolbar, text="🚀 去水印", command=self.process,
                  bg='#4CAF50', fg='white', font=('Arial', 11, 'bold')).pack(side=tk.RIGHT, padx=4)

        # 拖拽区域
        self.drop_frame = tk.Frame(self.root, bg='#f0f0f0', relief=tk.RIDGE, bd=2)
        self.drop_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.drop_label = tk.Label(
            self.drop_frame,
            text="🖼️  拖拽图片到这里\n或点 '📂 打开'",
            bg='#f0f0f0', fg='#666', font=('Arial', 16))
        self.drop_label.pack(expand=True)

        # 状态栏
        self.status = tk.Label(self.root, text="就绪 · v3 修复版", bd=1,
                               relief=tk.SUNKEN, anchor=tk.W)
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        # 拖拽
        if HAS_DND:
            self.drop_frame.drop_target_register(DND_FILES)
            self.drop_frame.dnd_bind('<<Drop>>', self.on_drop)
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind('<<Drop>>', self.on_drop)
        else:
            self.drop_label.config(text="⚠️ tkinterdnd2 未装\npip install tkinterdnd2")

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
            self.status.config(text=f"已加载: {os.path.basename(path)} "
                               f"({self.current_image.size[0]}x{self.current_image.size[1]})")
        except Exception as e:
            messagebox.showerror("错误", f"打开失败: {e}")

    def _show_image(self, img):
        max_size = (800, 520)
        img_copy = img.copy()
        img_copy.thumbnail(max_size, Image.Resampling.LANCZOS)

        from PIL import ImageTk
        photo = ImageTk.PhotoImage(img_copy)

        for widget in self.drop_frame.winfo_children():
            widget.destroy()

        canvas = tk.Canvas(self.drop_frame, bg='#f0f0f0', highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        canvas.create_image(
            max_size[0] // 2, max_size[1] // 2,
            image=photo, anchor=tk.CENTER
        )
        canvas.image = photo

    def process(self):
        if not self.current_image:
            messagebox.showwarning("提示", "先加载图片")
            return
        self.status.config(text="🔄 正在去水印...")
        self.root.update()

        try:
            result, region = remove_watermark_smart(
                self.current_image,
                self.region_hint.get(),
                self.sensitivity.get()
            )
            self.processed_image = result
            if region:
                self.status.config(text=f"✅ 完成 · 水印区域: {region}")
            else:
                self.status.config(
                    text="⚠️ 未检测到水印，请调低灵敏度或换个位置"
                )
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
