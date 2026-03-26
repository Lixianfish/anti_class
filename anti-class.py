import tkinter as tk
import threading
import time
import winsound
import ctypes
import os
import sys
import subprocess

# 如果通过 python.exe 直接运行，自动用 pythonw 重启以避免控制台闪烁（仅在开发时有用）
if getattr(sys, "frozen", False) is False and sys.executable.lower().endswith("python.exe"):
    # 防止无限重启：如果已经用 pythonw 启动（可通过环境判断），不会重启
    try:
        if not sys.argv[0].lower().endswith(".pyw"):
            subprocess.Popen([sys.executable.replace("python.exe", "pythonw.exe"), __file__])
            sys.exit()
    except Exception:
        # 如果重启失败就继续（比如没有 pythonw），不影响功能
        pass

# =====================
# 基础设置
# =====================
BLUE = "#0078D7"
RED = "#C00000"
PASSWORD = "LZ"
SLIDE_EXE = r"C:\Windows\System32\SlideToShutDown.exe"

# =====================
# Windows API helpers (ctypes)
# =====================
user32 = ctypes.windll.user32
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
LWA_ALPHA = 0x02
# =====================
# Win11稳定系统提示音
# =====================
def system_beep():
    """比 MessageBeep 更稳定的 Win11 系统提示音"""
    try:
        winsound.PlaySound(
            "SystemExclamation",
            winsound.SND_ALIAS | winsound.SND_ASYNC
        )
    except Exception:
        try:
            system_beep()
        except Exception:
            pass

def set_window_clickthrough(hwnd, enable=True, alpha=200):
    """
    使窗口可穿透鼠标（点击穿透），并设置分层 alpha（0-255）。
    hwnd: 窗口句柄（int）
    enable: True 开启穿透，False 取消穿透
    alpha: 透明度（0-255）仅用于 SetLayeredWindowAttributes
    """
    try:
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if enable:
            new_style = style | WS_EX_LAYERED | WS_EX_TRANSPARENT
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
            # 设置 alpha（仍然需要窗口是分层窗口）
            user32.SetLayeredWindowAttributes(hwnd, 0, int(alpha), LWA_ALPHA)
        else:
            new_style = style & ~(WS_EX_TRANSPARENT)  # 保持 WS_EX_LAYERED
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
            user32.SetLayeredWindowAttributes(hwnd, 0, int(alpha), LWA_ALPHA)
    except Exception:
        pass

def force_set_foreground(hwnd):
    """
    尝试强制把窗口置于前台（尽最大努力）。有系统限制时可能无效。
    """
    try:
        # 尝试常规方式
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        user32.ShowWindow(hwnd, 5)  # SW_SHOW
    except Exception:
        pass

# =====================
# 窗口管理类
# =====================
class WindowManager:
    """负责窗口居中、抖动、动画缩放等行为"""

    def __init__(self, win, width=420, height=220):
        self.win = win
        self.win_width = width
        self.win_height = height
        self.is_shaking = False

        # 初始化样式：禁止调整大小 & 使用工具栏样式（无最大化最小化）
        try:
            self.win.resizable(False, False)
            self.win.attributes("-toolwindow", True)
        except Exception:
            pass

        # 绑定事件
        self.win.bind("<FocusOut>", self.on_focus_out)
        self.win.bind("<Map>", lambda e: self.on_map())  # 窗口映射（显示）时触发
        self.win.protocol("WM_DELETE_WINDOW", lambda: self.shake_window())

        self.center_window()

    def center_window(self, width=None, height=None):
        """将窗口居中显示"""
        w = width or self.win_width
        h = height or self.win_height
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        self.win.update()

    def shake_window(self, intensity=12, duration=0.45):
        """阻塞式抖动（可读性好）"""
        if self.is_shaking:
            return
        self.is_shaking = True
        x = self.win.winfo_x()
        y = self.win.winfo_y()
        end_time = time.time() + duration
        system_beep()
        while time.time() < end_time:
            self.win.geometry(f"+{x + intensity}+{y}")
            self.win.update()
            time.sleep(0.02)
            self.win.geometry(f"+{x - intensity}+{y}")
            self.win.update()
            time.sleep(0.02)
        self.win.geometry(f"+{x}+{y}")
        self.win.update()
        self.is_shaking = False

    def on_map(self):
        """窗口刚显示时，尝试把自己带到前台"""
        try:
            hwnd = int(self.win.winfo_id())
            # 暂时置顶并尝试获得前台
            self.win.attributes("-topmost", True)
            self.win.lift()
            self.win.focus_force()
            force_set_foreground(hwnd)
            # 取消永久 topmost，如果你想永久置顶可去掉下一行
        except Exception:
            pass

    def on_focus_out(self, event):
        """失去焦点时：居中 + 抖动 + 提示音，并保持 topmost（以覆盖普通 PPT 窗口）"""
        # 播放提示音
        system_beep()
        # 居中并置顶
        self.center_window()
        try:
            self.win.attributes("-topmost", True)
            self.win.lift()
        except Exception:
            pass
        # 抖动
        self.shake_window()
        # 保持置顶（如果你不希望长期置顶可以把 True 改 False）
        try:
            self.win.attributes("-topmost", True)
        except Exception:
            pass

    def animate_initial_show(self):
        """
        窗口初次弹出动画：
        从胶囊尺寸平滑展开到屏幕中心（类似倒计时恢复动画）
        """
        try:
            # 获取屏幕中心目标
            screen_w = self.win.winfo_screenwidth()
            screen_h = self.win.winfo_screenheight()
            target_w = self.win_width
            target_h = self.win_height
            target_x = (screen_w - target_w) // 2
            target_y = (screen_h - target_h) // 2

            # 初始尺寸为胶囊尺寸
            from_w, from_h = 150, 60
            start_x = target_x + (target_w - from_w) // 2
            start_y = target_y + (target_h - from_h) // 2

            self.win.geometry(f"{from_w}x{from_h}+{start_x}+{start_y}")
            self.win.update()

            # 调用已有的 animate_expand，从小尺寸展开到中心
            self.animate_expand(from_w=from_w, from_h=from_h)
        except Exception:
            pass

    def animate_shrink(self, target_width=150, target_height=60,
                       target_x=60, target_y=40,
                       steps=18, duration=0.35):
        """
        完整动画：
        中心窗口 → 缩小 → 移动到胶囊位置
        """

        start_w = self.win.winfo_width()
        start_h = self.win.winfo_height()

        start_x = self.win.winfo_x()
        start_y = self.win.winfo_y()

        for i in range(steps):
            t = (i + 1) / steps

            w = int(start_w + (target_width - start_w) * t)
            h = int(start_h + (target_height - start_h) * t)

            x = int(start_x + (target_x - start_x) * t)
            y = int(start_y + (target_y - start_y) * t)

            self.win.geometry(f"{w}x{h}+{x}+{y}")
            self.win.update()

            time.sleep(duration / steps)

    def animate_expand(self, from_w=150, from_h=60,
                       steps=18, duration=0.35):
        """
        胶囊位置 → 展开 → 回到屏幕中心
        """

        screen_w = self.win.winfo_screenwidth()
        screen_h = self.win.winfo_screenheight()

        target_w = self.win_width
        target_h = self.win_height

        start_x = self.win.winfo_x()
        start_y = self.win.winfo_y()

        target_x = (screen_w - target_w) // 2
        target_y = (screen_h - target_h) // 2

        for i in range(steps):
            t = (i + 1) / steps

            w = int(from_w + (target_w - from_w) * t)
            h = int(from_h + (target_h - from_h) * t)

            x = int(start_x + (target_x - start_x) * t)
            y = int(start_y + (target_y - start_y) * t)

            self.win.geometry(f"{w}x{h}+{x}+{y}")
            self.win.update()

            time.sleep(duration / steps)

        self.center_window()


# =====================
# 倒计时胶囊（圆角、玻璃感、更透明、可穿透）
# =====================
# =====================
# 倒计时胶囊（Win11玻璃UI）
# =====================
class CountdownCapsule:
    """Win11风格玻璃倒计时胶囊（更透明 + 鼠标穿透）"""

    def __init__(self, duration, parent, x=40, y=40, click_through=True, alpha=140):
        self.duration = duration
        self.parent = parent
        self.click_through = click_through
        self.alpha = alpha

        # 更小尺寸
        self.width = 120
        self.height = 40

        self.capsule = tk.Toplevel()
        self.capsule.overrideredirect(True)
        self.capsule.attributes("-topmost", True)

        # 更透明
        self.capsule.attributes("-alpha", max(0.2, self.alpha / 255.0))

        self.capsule.configure(bg="#101010")
        self.capsule.geometry(f"{self.width}x{self.height}+{x}+{y}")

        # Canvas绘制玻璃UI
        self.canvas = tk.Canvas(
            self.capsule,
            width=self.width,
            height=self.height,
            bg="#101010",
            highlightthickness=0
        )
        self.canvas.pack()

        # 外层玻璃
        self.round_rect(
            2, 2,
            self.width - 2,
            self.height - 2,
            radius=14,
            fill="#000000"
        )

        # 内层高光
        self.round_rect(
            3, 3,
            self.width - 3,
            self.height - 3,
            radius=12,
            fill="#202020"
        )

        # 倒计时文字
        self.text_id = self.canvas.create_text(
            self.width // 2,
            self.height // 2,
            text="",
            fill="white",
            font=("Segoe UI", 13, "bold")
        )

        self.capsule.update_idletasks()

        # 设置鼠标穿透
        if self.click_through:
            try:
                hwnd = int(self.capsule.winfo_id())
                set_window_clickthrough(hwnd, enable=True, alpha=self.alpha)
            except Exception:
                pass

    def round_rect(self, x1, y1, x2, y2, radius=12, **kwargs):
        points = [
            x1+radius, y1,
            x2-radius, y1,
            x2, y1,
            x2, y1+radius,
            x2, y2-radius,
            x2, y2,
            x2-radius, y2,
            x1+radius, y2,
            x1, y2,
            x1, y2-radius,
            x1, y1+radius,
            x1, y1
        ]
        self.canvas.create_polygon(points, smooth=True, **kwargs)

    def start(self, callback=None):
        """后台线程倒计时"""

        def runner():

            for i in range(self.duration, 0, -1):

                try:
                    self.canvas.itemconfig(self.text_id, text=f"{i}s")
                    self.capsule.update()
                except:
                    pass

                time.sleep(1)

            try:
                self.capsule.destroy()
            except:
                pass

            try:
                self.parent.deiconify()
            except:
                pass

            if callback:
                callback()

        threading.Thread(target=runner, daemon=True).start()

    def round_rect(self, x1, y1, x2, y2, radius=12, **kwargs):
        points = [
            x1+radius, y1,
            x2-radius, y1,
            x2, y1,
            x2, y1+radius,
            x2, y2-radius,
            x2, y2,
            x2-radius, y2,
            x1+radius, y2,
            x1, y2,
            x1, y2-radius,
            x1, y1+radius,
            x1, y1
        ]
        self.canvas.create_polygon(points, smooth=True, **kwargs)

    def start(self, callback=None):
        """在后台线程运行倒计时（不阻塞主线程）"""
        def runner():
            for i in range(self.duration, 0, -1):
                try:
                    self.canvas.itemconfig(self.text_id, text=f"{i}s")
                    self.capsule.update()
                except Exception:
                    pass
                time.sleep(1)
            try:
                self.capsule.destroy()
            except Exception:
                pass
            try:
                # 恢复主窗口
                self.parent.deiconify()
            except Exception:
                pass
            if callback:
                callback()

        threading.Thread(target=runner, daemon=True).start()

# =====================
# 三阶段主程序（保留你的逻辑，改进聚焦/滑动关机启动）
# =====================
class EndClassApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("反拖堂程序2.0")
        self.root.configure(bg=BLUE)

        # 禁止最大化/最小化与调整大小
        self.root.resizable(False, False)
        try:
            self.root.attributes("-toolwindow", True)
        except Exception:
            pass

        # ---------------------------
        # 初始化窗口初始尺寸为胶囊大小
        # ---------------------------
        self.root.geometry("150x60")  # 这里的尺寸应和你的 animate_shrink/expand 的胶囊尺寸一致
        self.root.update()

        self.win_manager = WindowManager(self.root)

        # 阶段控制：1=第一次弹窗，2=第二次弹窗，3=最终密码验证
        self.stage = 1

        # 防止重复启动滑动关机
        self.shutdown_started = False

        # 初始显示
        self.show_stage()

        # ---------------------------
        # 延迟调用窗口首次展开动画
        # ---------------------------
        self.root.after(100, lambda: self.win_manager.animate_expand(
            from_w=150, from_h=60
        ))

        # 播放一次系统提示音（每次窗口弹出会调用）
        system_beep()

        # 尝试初始化焦点（解决 "必须先点击窗口" 的问题）
        self.root.after(150, self.init_focus_system)

    def init_focus_system(self):
        """尝试把窗口带到前台并获取焦点（尽量）"""
        try:
            hwnd = int(self.root.winfo_id())
            # 临时置顶 + lift + focus_force + 强制前台
            self.root.attributes("-topmost", True)
            self.root.lift()
            self.root.focus_force()
            force_set_foreground(hwnd)
            # 0.3s 后保持 topmost（如果你不想长期置顶可改为 False）
            self.root.after(300, lambda: self.root.attributes("-topmost", True))
        except Exception:
            pass

    # ---------- 根据阶段显示 UI ----------
    def show_stage(self):
        # 每次切换阶段播一次音
        system_beep()

        for w in self.root.winfo_children():
            w.destroy()

        if self.stage == 1:
            # 第一次弹窗：提前2分钟下课 / 继续上课（2 分钟后提示）
            tk.Label(self.root, text="⏰ 提前2分钟下课？",
                     font=("Microsoft YaHei", 18), bg=BLUE, fg="white").pack(pady=15)
            tk.Button(self.root, text="提前下课", font=("Microsoft YaHei", 16),
                      width=16, command=self.slide_shutdown).pack(pady=10)
            tk.Button(self.root, text="继续", font=("Microsoft YaHei", 16),
                      width=16, command=self.continue_for_2min).pack(pady=10)

        elif self.stage == 2:
            # 第二次弹窗：下课 / 拖堂3分钟
            tk.Label(self.root, text="⏰ 下课还是再拖堂3分钟？",
                     font=("Microsoft YaHei", 18), bg=BLUE, fg="white").pack(pady=15)
            tk.Button(self.root, text="下课", font=("Microsoft YaHei", 16),
                      width=16, command=self.slide_shutdown).pack(pady=10)
            tk.Button(self.root, text="拖堂3分钟", font=("Microsoft YaHei", 16),
                      width=16, command=self.delay_3min_stage).pack(pady=10)

        elif self.stage == 3:
            # 第三次弹窗：密码验证
            self.build_final_ui()

    # ---------- 第一次“继续”：等待 2 分钟再提示 ----------
    def continue_for_2min(self):
        system_beep()
        # 隐藏主窗口（让胶囊显眼），不缩放
        self.win_manager.animate_shrink()
        self.root.withdraw()
        # 120 秒倒计时胶囊（更小更透明且可穿透）
        CountdownCapsule(120, self.root, x=60, y=40, click_through=True, alpha=150).start(callback=self.after_continue_2min)

    def after_continue_2min(self):
        try:
            self.root.deiconify()
        except Exception:
            pass
        system_beep()
        self.stage = 2
        self.show_stage()

    # ---------- 拖堂流程（3 分钟） ----------
    def delay_3min_stage(self):
        system_beep()
        self.win_manager.animate_shrink()
        self.root.withdraw()
        CountdownCapsule(180, self.root, x=60, y=40, click_through=True, alpha=150).start(callback=self.after_delay_stage)

    def after_delay_stage(self):
        try:
            self.root.deiconify()
        except Exception:
            pass
        self.win_manager.animate_expand()
        self.stage += 1
        self.show_stage()

    # ---------- 最终密码验证阶段 ----------
    def build_final_ui(self):
        for w in self.root.winfo_children():
            w.destroy()

        self.root.configure(bg=RED)
        tk.Label(self.root, text="输入密码可关闭程序",
                 font=("Microsoft YaHei", 16), fg="white", bg=RED).pack(pady=10)

        self.pw_entry = tk.Entry(self.root, font=("Consolas", 16),
                                 show="*", justify="center")
        self.pw_entry.pack(pady=10)
        self.pw_entry.focus()

        tk.Button(self.root, text="确认", font=("Microsoft YaHei", 14),
                  width=12, command=self.check_password).pack(pady=10)

        tk.Button(self.root, text="立刻下课",
                  font=("Microsoft YaHei", 14),
                  width=12, command=self.slide_shutdown).pack()

    # ---------- 密码验证 ----------
    def check_password(self):
        if self.pw_entry.get() == PASSWORD:
            # 密码正确：退出程序
            try:
                self.root.destroy()
            except Exception:
                pass
        else:
            self.pw_entry.delete(0, tk.END)
            system_beep()
            self.win_manager.shake_window()

    # ---------- 下课（滑动关机） ----------
    def slide_shutdown(self):
        """调用 Windows 内置滑动关机界面（无黑窗、无延迟）"""
        if getattr(self, "shutdown_started", False):
            return
        self.shutdown_started = True

        # 隐藏主窗口（程序继续运行直到系统关机）

        if os.path.exists(SLIDE_EXE):
            # 使用 Popen 非阻塞启动（不会弹出控制台）
            try:
                subprocess.Popen([SLIDE_EXE])
            except Exception:
                # 兜底：使用 CREATE_NO_WINDOW
                subprocess.Popen([SLIDE_EXE], creationflags=0x08000000)
        else:
            system_beep()
            try:
                tk.messagebox.showinfo("提示", "未找到 SlideToShutDown.exe，无法启动滑动关机。")
            except Exception:
                pass

    # ---------- 启动主循环 ----------
    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    EndClassApp().run()
