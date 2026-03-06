import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import uuid
import threading
import time
import ctypes
import sys
import keyboard  # Used for key capture in settings
from core import EngineController
import os
import ttkbootstrap as tb  # Modern UI
try:
    import psutil
except ImportError:
    psutil = None

class TaskDialog(tb.Toplevel):
    def __init__(self, parent, initial_data=None):
        super().__init__(master=parent)
        self.title("编辑任务" if initial_data else "添加任务")
        self.geometry("320x400")
        self.resizable(False, False)
        self.result = None
        self.initial_data = initial_data
        
        self._init_ui()
        
        if initial_data:
            self._load_data(initial_data)
            
        # Center dialog
        self.transient(parent)
        self.grab_set()
        self.focus_set()
        
        # Center on parent
        self.place_window_center()

    def place_window_center(self):
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    def _init_ui(self):
        frame = tb.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # Key Selection
        tb.Label(frame, text="目标按键:", font=("微软雅黑", 10)).pack(anchor="w")
        key_frame = tb.Frame(frame)
        key_frame.pack(fill=tk.X, pady=5)
        
        self.key_var = tk.StringVar(value="a")
        self.key_entry = tb.Entry(key_frame, textvariable=self.key_var, state='readonly')
        self.key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        self.capture_btn = tb.Button(key_frame, text="设置按键", command=self._capture_key, bootstyle="info-outline")
        self.capture_btn.pack(side=tk.LEFT)
        
        # Mouse Buttons (Alternative)
        tb.Label(frame, text="或选择鼠标按键:", font=("微软雅黑", 10)).pack(anchor="w", pady=(10, 0))
        self.mouse_var = tk.StringVar()
        mouse_cb = tb.Combobox(frame, textvariable=self.mouse_var, values=["", "left", "right", "middle"])
        mouse_cb.pack(fill=tk.X, pady=5)
        mouse_cb.bind("<<ComboboxSelected>>", self._on_mouse_select)
        
        # Interval
        tb.Label(frame, text="连点间隔 (毫秒):", font=("微软雅黑", 10)).pack(anchor="w", pady=(10, 0))
        self.interval_var = tk.IntVar(value=100)
        tb.Entry(frame, textvariable=self.interval_var).pack(fill=tk.X, pady=5)
        
        # Mode
        tb.Label(frame, text="触发模式:", font=("微软雅黑", 10)).pack(anchor="w", pady=(10, 0))
        self.mode_var = tk.StringVar(value="toggle")
        tb.Radiobutton(frame, text="开关模式 (按一下开/关)", variable=self.mode_var, value="toggle", bootstyle="primary").pack(anchor="w", pady=2)
        tb.Radiobutton(frame, text="按压模式 (按住连点)", variable=self.mode_var, value="hold", bootstyle="primary").pack(anchor="w", pady=2)
        
        # Buttons
        btn_frame = tb.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(24, 8))
        tb.Button(btn_frame, text="保存", command=self._save, bootstyle="success").pack(side=tk.RIGHT, padx=5)
        tb.Button(btn_frame, text="取消", command=self.destroy, bootstyle="secondary").pack(side=tk.RIGHT)

    def _on_mouse_select(self, event):
        val = self.mouse_var.get()
        if val:
            self.key_var.set(val)

    def _capture_key(self):
        self.capture_btn.config(text="请按键...", state='disabled')
        self.update()
        
        def wait_key():
            event = keyboard.read_event(suppress=True)
            if event.event_type == 'down':
                key = event.name
                self.after(0, lambda: self._set_key(key))

        threading.Thread(target=wait_key, daemon=True).start()

    def _set_key(self, key):
        self.key_var.set(key)
        self.mouse_var.set("") # Clear mouse selection
        self.capture_btn.config(text="设置按键", state='normal')

    def _load_data(self, data):
        self.key_var.set(data['key'])
        self.interval_var.set(data['interval'])
        self.mode_var.set(data['mode'])
        if data['key'] in ['left', 'right', 'middle']:
            self.mouse_var.set(data['key'])

    def _save(self):
        try:
            interval = self.interval_var.get()
            if interval <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("错误", "间隔必须是正整数。")
            return
            
        self.result = {
            "key": self.key_var.get(),
            "interval": interval,
            "mode": self.mode_var.get()
        }
        self.destroy()

class MainApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SoloKeyClicker - 未命名配置")
        self.root.geometry("760x600")
        self.root.overrideredirect(False)
        self.root.protocol("WM_DELETE_WINDOW", self._close_window)
        self._apply_app_icon()
        self.current_theme = "darkly"
        self.style = tb.Style(theme=self.current_theme)
        self._setup_styles()
        self.engine = EngineController()
        self.tasks_data = []
        self.current_config_name = "未命名配置"
        self.injection_mode_map = {"自动": "auto", "系统": "winapi", "硬件": "hardware"}
        self.injection_mode_reverse_map = {v: k for k, v in self.injection_mode_map.items()}
        self._f8_hotkey_ref = None
        self._last_f8_toggle_ts = 0.0
        self.process = psutil.Process(os.getpid()) if psutil else None
        if self.process:
            self.process.cpu_percent(interval=None)
        self._init_ui()
        self._bind_f8_shortcut()
        self._load_default_config_on_startup()
        self._start_monitor()
        self._center_window()

    def _setup_styles(self):
        self.style.configure("AppTitle.TLabel", font=("微软雅黑", 15, "bold"))
        self.style.configure("AppSubTitle.TLabel", font=("微软雅黑", 9))
        self.style.configure("SectionTitle.TLabel", font=("微软雅黑", 10, "bold"))
        if self.current_theme == "darkly":
            tree_bg = "#1f2630"
            tree_fg = "#f1f3f5"
            selected_bg = "#375a7f"
        else:
            tree_bg = "#ffffff"
            tree_fg = "#1f2328"
            selected_bg = "#4f8cff"
        self.style.configure("Treeview", font=("微软雅黑", 10), rowheight=30, background=tree_bg, fieldbackground=tree_bg, foreground=tree_fg)
        self.style.configure("Treeview.Heading", font=("微软雅黑", 10, "bold"))
        self.style.map("Treeview", background=[("selected", selected_bg)], foreground=[("selected", "#ffffff")])

    def _apply_theme(self, theme_name):
        self.current_theme = theme_name
        self.style.theme_use(theme_name)
        self._setup_styles()
        if theme_name == "darkly":
            self.theme_btn_var.set("☀ 浅色")
        else:
            self.theme_btn_var.set("🌙 深色")

    def _toggle_theme(self):
        target = "cosmo" if self.current_theme == "darkly" else "darkly"
        self._apply_theme(target)

    def _close_window(self):
        if self._f8_hotkey_ref is not None:
            try:
                keyboard.remove_hotkey(self._f8_hotkey_ref)
            except Exception:
                pass
            self._f8_hotkey_ref = None
        self.root.destroy()

    def _bind_f8_shortcut(self):
        self.root.bind_all("<F8>", lambda _e: self._toggle_hook_listener_hotkey())
        try:
            self._f8_hotkey_ref = keyboard.add_hotkey("f8", lambda: self.root.after(0, self._toggle_hook_listener_hotkey), suppress=False)
        except Exception:
            self._f8_hotkey_ref = None

    def _toggle_hook_listener_hotkey(self):
        now = time.perf_counter()
        if now - self._last_f8_toggle_ts < 0.25:
            return
        self._last_f8_toggle_ts = now
        self._toggle_hook_listener()

    def _center_window(self):
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')

    def _init_ui(self):
        main_container = tb.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        header = tb.Frame(main_container)
        header.pack(fill=tk.X, pady=(0, 8))
        tb.Label(header, text="SoloKeyClicker", style="AppTitle.TLabel").pack(side=tk.LEFT)
        tb.Label(header, text="键盘连点控制台", style="AppSubTitle.TLabel", bootstyle="secondary").pack(side=tk.LEFT, padx=2, pady=6)
        self.theme_btn_var = tk.StringVar(value="☀ 浅色")
        self.theme_toggle_label = tb.Label(header, textvariable=self.theme_btn_var, bootstyle="info", cursor="hand2")
        self.theme_toggle_label.pack(side=tk.RIGHT, padx=4)
        self.theme_toggle_label.bind("<Button-1>", lambda _e: self._toggle_theme())

        action_card = tb.Frame(main_container, borderwidth=1, relief="solid")
        action_card.pack(fill=tk.X, pady=(0, 10))
        action_inner = tb.Frame(action_card)
        action_inner.pack(fill=tk.X, padx=10, pady=10)
        tb.Label(action_inner, text="任务管理", style="SectionTitle.TLabel").pack(side=tk.LEFT, padx=(0, 8))
        tb.Button(action_inner, text="添加", command=self._add_task, bootstyle="success-outline", width=7).pack(side=tk.LEFT, padx=3)
        tb.Button(action_inner, text="编辑", command=self._edit_task, bootstyle="info-outline", width=7).pack(side=tk.LEFT, padx=3)
        tb.Button(action_inner, text="删除", command=self._delete_task, bootstyle="danger-outline", width=7).pack(side=tk.LEFT, padx=3)
        tb.Separator(action_inner, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=12)
        tb.Label(action_inner, text="配置", style="SectionTitle.TLabel").pack(side=tk.LEFT, padx=(0, 8))
        tb.Button(action_inner, text="导入", command=self._import_config, bootstyle="secondary-outline", width=7).pack(side=tk.LEFT, padx=3)
        tb.Button(action_inner, text="导出", command=self._export_config, bootstyle="secondary-outline", width=7).pack(side=tk.LEFT, padx=3)
        tb.Button(action_inner, text="设默认", command=self._save_default_config, bootstyle="secondary-outline", width=7).pack(side=tk.LEFT, padx=3)

        list_card = tb.Frame(main_container, borderwidth=1, relief="solid")
        list_card.pack(fill=tk.BOTH, expand=True)
        list_header = tb.Frame(list_card)
        list_header.pack(fill=tk.X, padx=10, pady=(8, 4))
        tb.Label(list_header, text="任务列表", style="SectionTitle.TLabel").pack(side=tk.LEFT)

        tree_frame = tb.Frame(list_card)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        columns = ("key", "interval", "mode", "status")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("key", text="按键 / 按钮")
        self.tree.heading("interval", text="间隔 (ms)")
        self.tree.heading("mode", text="触发模式")
        self.tree.heading("status", text="状态")

        self.tree.column("key", width=120, anchor="center")
        self.tree.column("interval", width=100, anchor="center")
        self.tree.column("mode", width=130, anchor="center")
        self.tree.column("status", width=110, anchor="center")

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<Double-1>", lambda e: self._edit_task())

        control_card = tb.Frame(main_container, borderwidth=1, relief="solid")
        control_card.pack(fill=tk.X, pady=(10, 0))
        cp_inner = tb.Frame(control_card)
        cp_inner.pack(fill=tk.X, padx=12, pady=10)

        self.mutex_var = tk.BooleanVar(value=False)
        tb.Checkbutton(cp_inner, text="独立模式（启动任务时自动关闭其他任务）", variable=self.mutex_var, command=self._toggle_mutex, bootstyle="round-toggle").pack(side=tk.LEFT)
        self.debug_mode_var = tk.BooleanVar(value=True)
        tb.Checkbutton(cp_inner, text="Debug模式", variable=self.debug_mode_var, command=self._toggle_debug_mode, bootstyle="round-toggle").pack(side=tk.LEFT, padx=(10, 0))
        tb.Label(cp_inner, text="注入模式", style="SectionTitle.TLabel").pack(side=tk.LEFT, padx=(14, 6))
        self.injection_mode_var = tk.StringVar(value="自动")
        self.injection_mode_cb = tb.Combobox(cp_inner, textvariable=self.injection_mode_var, values=["自动", "系统", "硬件"], width=7, state="readonly")
        self.injection_mode_cb.pack(side=tk.LEFT)
        self.injection_mode_cb.bind("<<ComboboxSelected>>", self._on_injection_mode_change)

        right_panel = tb.Frame(cp_inner)
        right_panel.pack(side=tk.RIGHT)
        self.hook_status_var = tk.StringVar(value="监听中")
        self.status_badge = tb.Label(right_panel, textvariable=self.hook_status_var, bootstyle="success", font=("微软雅黑", 9, "bold"), padding=(8, 4))
        self.status_badge.pack(side=tk.LEFT, padx=10)
        self.hook_btn_var = tk.StringVar(value="停止监听")
        self.hook_toggle_btn = tb.Button(right_panel, textvariable=self.hook_btn_var, command=self._toggle_hook_listener, bootstyle="danger-outline", width=10)
        self.hook_toggle_btn.pack(side=tk.LEFT)

        self.status_bar_var = tk.StringVar(value=f"当前配置: {self.current_config_name} | 建议以管理员身份运行")
        self.monitor_var = tk.StringVar(value="监听: 监听中 | 运行任务: 0")
        status_bar_wrap = tb.Frame(self.root)
        status_bar_wrap.pack(fill=tk.X, side=tk.BOTTOM)
        tb.Label(status_bar_wrap, textvariable=self.status_bar_var, bootstyle="secondary", font=("微软雅黑", 9), padding=(10, 3)).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tb.Label(status_bar_wrap, textvariable=self.monitor_var, bootstyle="secondary", font=("微软雅黑", 9), padding=(10, 3)).pack(side=tk.RIGHT)
        self._apply_theme(self.current_theme)

    def _toggle_hook_listener(self):
        current_active = self.engine.is_hook_active()
        new_active = not current_active
        
        self.engine.set_hook_active(new_active)
        
        if new_active:
            self.hook_status_var.set("监听中")
            self.status_badge.configure(bootstyle="success")
            self.hook_btn_var.set("停止监听")
            self.hook_toggle_btn.configure(bootstyle="danger-outline")
        else:
            self.engine.stop_all()
            self.hook_status_var.set("已暂停")
            self.status_badge.configure(bootstyle="danger")
            self.hook_btn_var.set("开始监听")
            self.hook_toggle_btn.configure(bootstyle="success-outline")
        self._update_monitor_status()

    def _add_task(self):
        dlg = TaskDialog(self.root)
        self.root.wait_window(dlg)
        if dlg.result:
            task_id = str(uuid.uuid4())
            item = dlg.result
            item['id'] = task_id
            self.tasks_data.append(item)
            self._sync_task_to_engine(item)
            self._refresh_list()

    def _edit_task(self):
        selected = self.tree.selection()
        if not selected:
            return
        
        idx = self.tree.index(selected[0])
        task_data = self.tasks_data[idx]
        
        dlg = TaskDialog(self.root, initial_data=task_data)
        self.root.wait_window(dlg)
        if dlg.result:
            # Update data
            task_data.update(dlg.result)
            self._sync_task_to_engine(task_data)
            self._refresh_list()

    def _delete_task(self):
        selected = self.tree.selection()
        if not selected:
            return
        idx = self.tree.index(selected[0])
        task_data = self.tasks_data[idx]
        
        # Remove from engine
        self.engine.remove_task(task_data['id'])
        
        # Remove from list
        self.tasks_data.pop(idx)
        self._refresh_list()

    def _sync_task_to_engine(self, item):
        self.engine.add_task(
            task_id=item['id'],
            target_name=item['key'],
            interval_ms=item['interval'],
            mode=item['mode']
        )

    def _refresh_list(self):
        # Clear tree
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Repopulate
        for task in self.tasks_data:
            # Get real-time status
            is_running = self.engine.get_task_status(task['id'])
            status = "运行中" if is_running else "空闲"
            
            mode_display = "开关模式" if task['mode'] == 'toggle' else "按压模式"
            
            self.tree.insert("", "end", values=(
                task['key'],
                f"{task['interval']} ms",
                mode_display,
                status
            ))

    def _toggle_mutex(self):
        self.engine.set_mutex_mode(self.mutex_var.get())

    def _toggle_debug_mode(self):
        self._update_monitor_status()

    def _on_injection_mode_change(self, event=None):
        selected = self.injection_mode_var.get()
        mode = self.injection_mode_map.get(selected, "auto")
        self.engine.set_injection_mode(mode)
        self._update_monitor_status()

    def _update_title(self):
        self.root.title(f"SoloKeyClicker - {self.current_config_name}")
        self.status_bar_var.set(f"当前配置: {self.current_config_name}")

    def _update_monitor_status(self):
        running_count = 0
        for task in self.tasks_data:
            if self.engine.get_task_status(task['id']):
                running_count += 1
        hook_text = "监听中" if self.engine.is_hook_active() else "已暂停"
        inject_text = self.engine.get_injection_state()
        debug_text = self.engine.get_driver_release_debug()
        if self.process:
            cpu_usage = self.process.cpu_percent(interval=None)
            mem_usage = self.process.memory_info().rss / (1024 * 1024)
            perf_text = f"CPU: {cpu_usage:.1f}% | 内存: {mem_usage:.1f}MB"
        else:
            perf_text = "CPU: -- | 内存: --"
        base_text = f"监听: {hook_text} | 运行任务: {running_count} | 注入: {inject_text} | {perf_text}"
        if self.debug_mode_var.get():
            self.monitor_var.set(f"{base_text} | {debug_text}")
        else:
            self.monitor_var.set(base_text)

    def _get_app_dir(self):
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    def _get_resource_path(self, filename):
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            return os.path.join(sys._MEIPASS, filename)
        return os.path.join(self._get_app_dir(), filename)

    def _apply_app_icon(self):
        icon_path = self._get_resource_path("icon.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(default=icon_path)
            except:
                pass

    def _get_default_config_path(self):
        return os.path.join(self._get_app_dir(), "default_config.json")

    def _build_config_payload(self):
        theme_mode = "dark" if self.current_theme == "darkly" else "light"
        return {
            "mutex_mode": self.mutex_var.get(),
            "independent_mode": self.mutex_var.get(),
            "debug_mode": self.debug_mode_var.get(),
            "theme_mode": theme_mode,
            "injection_mode": self.engine.get_injection_mode(),
            "tasks": self.tasks_data
        }

    def _load_config_from_path(self, path, show_success=True):
        with open(path, 'r') as f:
            config = json.load(f)
        independent_mode = config.get("independent_mode", config.get("mutex_mode", False))
        self.mutex_var.set(bool(independent_mode))
        self._toggle_mutex()
        self.debug_mode_var.set(bool(config.get("debug_mode", True)))
        theme_mode = config.get("theme_mode")
        if theme_mode == "dark":
            self._apply_theme("darkly")
        elif theme_mode == "light":
            self._apply_theme("cosmo")
        injection_mode = config.get("injection_mode", "auto")
        self.engine.set_injection_mode(injection_mode)
        self.injection_mode_var.set(self.injection_mode_reverse_map.get(injection_mode, "自动"))
        self.engine.stop_all()
        self.tasks_data = []
        for task in config.get("tasks", []):
            if 'id' not in task:
                task['id'] = str(uuid.uuid4())
            self.tasks_data.append(task)
            self._sync_task_to_engine(task)
        self._refresh_list()
        filename = os.path.basename(path)
        self.current_config_name = os.path.splitext(filename)[0]
        self._update_title()
        self._update_monitor_status()
        if show_success:
            messagebox.showinfo("成功", "配置已加载。")

    def _load_default_config_on_startup(self):
        path = self._get_default_config_path()
        if os.path.exists(path):
            try:
                self._load_config_from_path(path, show_success=False)
            except Exception as e:
                messagebox.showwarning("警告", f"默认配置加载失败: {e}")

    def _export_config(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON Config", "*.json")])
        if path:
            try:
                with open(path, 'w') as f:
                    json.dump(self._build_config_payload(), f, indent=2)
                
                # Update config name display
                filename = os.path.basename(path)
                self.current_config_name = os.path.splitext(filename)[0]
                self._update_title()
                
                messagebox.showinfo("成功", "配置已保存。")
            except Exception as e:
                messagebox.showerror("错误", str(e))

    def _import_config(self):
        path = filedialog.askopenfilename(filetypes=[("JSON Config", "*.json")])
        if path:
            try:
                self._load_config_from_path(path, show_success=True)
            except Exception as e:
                messagebox.showerror("错误", f"加载配置失败: {e}")

    def _save_default_config(self):
        path = self._get_default_config_path()
        try:
            with open(path, 'w') as f:
                json.dump(self._build_config_payload(), f, indent=2)
            messagebox.showinfo("成功", f"已设为默认配置: {path}")
        except Exception as e:
            messagebox.showerror("错误", f"设置默认配置失败: {e}")

    def _start_monitor(self):
        # Periodically refresh status (e.g. every 500ms)
        # Only need to update status column
        for i, task in enumerate(self.tasks_data):
            is_running = self.engine.get_task_status(task['id'])
            status = "运行中" if is_running else "空闲"
            
            # Treeview items are stored by ID, but we didn't set ID.
            # Get child by index
            children = self.tree.get_children()
            if i < len(children):
                self.tree.set(children[i], "status", status)
        self._update_monitor_status()
        self.root.after(200, self._start_monitor)

if __name__ == "__main__":
    # Ensure High DPI awareness
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SoloDriver.SoloClick")
    except:
        pass

    root = tb.Window(themename="darkly")
    app = MainApp(root)
    root.mainloop()
