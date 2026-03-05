import threading
import time
import ctypes
from ctypes import wintypes
import queue
from typing import Dict, Optional, Callable, List
try:
    import interception as hw_interception
except Exception:
    hw_interception = None

# --- Windows API Constants & Structures ---

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208

LLKHF_INJECTED = 0x00000010

# Mouse Constants
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040

# Keyboard Constants
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_EXTENDEDKEY = 0x0001
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MAPVK_VK_TO_VSC = 0
MK_LBUTTON = 0x0001
MK_RBUTTON = 0x0002
MK_MBUTTON = 0x0010

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]

ULONG_PTR = wintypes.WPARAM

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]

class INPUTUNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", INPUTUNION),
    ]

class POINT(ctypes.Structure):
    _fields_ = [
        ("x", wintypes.LONG),
        ("y", wintypes.LONG),
    ]

# C Types for Hook
# LRESULT is 64-bit on x64, 32-bit on x86
LRESULT = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long
HOOKRPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Define Argument Types for 64-bit Compatibility
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKRPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK

user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL

user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL

kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.GetAsyncKeyState.argtypes = [wintypes.INT]
user32.GetAsyncKeyState.restype = wintypes.SHORT
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(POINT)]
user32.ScreenToClient.restype = wintypes.BOOL

# --- Helper: VK Code Mapping ---
VK_MAP = {
    'left_button': 0x01, 'right_button': 0x02, 'middle_button': 0x04,
    'backspace': 0x08, 'tab': 0x09, 'enter': 0x0D, 'shift': 0x10, 'ctrl': 0x11, 'alt': 0x12,
    'caps_lock': 0x14, 'esc': 0x1B, 'space': 0x20, 'page_up': 0x21, 'page_down': 0x22,
    'end': 0x23, 'home': 0x24, 'left': 0x25, 'up': 0x26, 'right': 0x27, 'down': 0x28,
    'insert': 0x2D, 'delete': 0x2E,
    '0': 0x30, '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34, 
    '5': 0x35, '6': 0x36, '7': 0x37, '8': 0x38, '9': 0x39,
    'a': 0x41, 'b': 0x42, 'c': 0x43, 'd': 0x44, 'e': 0x45, 'f': 0x46, 'g': 0x47, 'h': 0x48,
    'i': 0x49, 'j': 0x4A, 'k': 0x4B, 'l': 0x4C, 'm': 0x4D, 'n': 0x4E, 'o': 0x4F, 'p': 0x50,
    'q': 0x51, 'r': 0x52, 's': 0x53, 't': 0x54, 'u': 0x55, 'v': 0x56, 'w': 0x57, 'x': 0x58,
    'y': 0x59, 'z': 0x5A,
    'f1': 0x70, 'f2': 0x71, 'f3': 0x72, 'f4': 0x73, 'f5': 0x74, 'f6': 0x75,
    'f7': 0x76, 'f8': 0x77, 'f9': 0x78, 'f10': 0x79, 'f11': 0x7A, 'f12': 0x7B,
}

def get_vk_from_name(name):
    name = name.lower()
    if name in VK_MAP:
        return VK_MAP[name]
    if len(name) == 1:
        ret = user32.VkKeyScanA(ctypes.c_char(name.encode()))
        if ret != -1:
            return ret & 0xFF
    return 0

EXTENDED_KEY_NAMES = {
    "right", "down", "up", "left", "insert", "delete", "home", "end", "page_up", "page_down"
}
KEY_HOLD_SECONDS = 0.006
MOUSE_HOLD_SECONDS = 0.004
TOGGLE_MIN_PRESS_SECONDS = 0.028
TOGGLE_STOP_HOLD_SECONDS = 0.09

def _send_input_keyboard(vk_code, use_scancode, extended, hold_seconds):
    scan_code = user32.MapVirtualKeyW(vk_code, MAPVK_VK_TO_VSC)
    key_flags = KEYEVENTF_EXTENDEDKEY if extended else 0
    if use_scancode:
        key_flags |= KEYEVENTF_SCANCODE
        wvk = 0
        wscan = scan_code
    else:
        wvk = vk_code
        wscan = 0
    down = INPUT(
        type=INPUT_KEYBOARD,
        union=INPUTUNION(ki=KEYBDINPUT(wvk, wscan, key_flags, 0, 0))
    )
    up = INPUT(
        type=INPUT_KEYBOARD,
        union=INPUTUNION(ki=KEYBDINPUT(wvk, wscan, key_flags | KEYEVENTF_KEYUP, 0, 0))
    )
    down_inputs = (INPUT * 1)(down)
    up_inputs = (INPUT * 1)(up)
    down_ok = user32.SendInput(1, down_inputs, ctypes.sizeof(INPUT)) == 1
    if hold_seconds > 0:
        time.sleep(hold_seconds)
    up_ok = user32.SendInput(1, up_inputs, ctypes.sizeof(INPUT)) == 1
    return down_ok and up_ok

def _build_key_lparam(scan_code, extended, is_key_up):
    value = 1 | ((scan_code & 0xFF) << 16)
    if extended:
        value |= (1 << 24)
    if is_key_up:
        value |= (1 << 30) | (1 << 31)
    return value

def _postmessage_keyboard(vk_code, target_name, hold_seconds):
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    extended = target_name in EXTENDED_KEY_NAMES
    scan_code = user32.MapVirtualKeyW(vk_code, MAPVK_VK_TO_VSC)
    down_lparam = _build_key_lparam(scan_code, extended, False)
    up_lparam = _build_key_lparam(scan_code, extended, True)
    down_ok = bool(user32.PostMessageW(hwnd, WM_KEYDOWN, vk_code, down_lparam))
    time.sleep(hold_seconds)
    up_ok = bool(user32.PostMessageW(hwnd, WM_KEYUP, vk_code, up_lparam))
    return down_ok and up_ok

def send_keyboard_click(vk_code, target_name, hold_seconds=None):
    press_seconds = KEY_HOLD_SECONDS if hold_seconds is None else hold_seconds
    extended = target_name in EXTENDED_KEY_NAMES
    if _send_input_keyboard(vk_code, True, extended, press_seconds):
        return True
    if _send_input_keyboard(vk_code, False, extended, press_seconds):
        return True
    user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY if extended else 0, 0)
    time.sleep(press_seconds)
    user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP | (KEYEVENTF_EXTENDEDKEY if extended else 0), 0)
    return _postmessage_keyboard(vk_code, target_name, press_seconds)

def _postmessage_mouse(target_name, hold_seconds):
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    point = POINT()
    if not user32.GetCursorPos(ctypes.byref(point)):
        return False
    if not user32.ScreenToClient(hwnd, ctypes.byref(point)):
        return False
    lparam = ((point.y & 0xFFFF) << 16) | (point.x & 0xFFFF)
    if target_name == 'left':
        down_msg, up_msg, wparam = WM_LBUTTONDOWN, WM_LBUTTONUP, MK_LBUTTON
    elif target_name == 'right':
        down_msg, up_msg, wparam = WM_RBUTTONDOWN, WM_RBUTTONUP, MK_RBUTTON
    elif target_name == 'middle':
        down_msg, up_msg, wparam = WM_MBUTTONDOWN, WM_MBUTTONUP, MK_MBUTTON
    else:
        return False
    down_ok = bool(user32.PostMessageW(hwnd, down_msg, wparam, lparam))
    time.sleep(hold_seconds)
    up_ok = bool(user32.PostMessageW(hwnd, up_msg, 0, lparam))
    return down_ok and up_ok

def send_mouse_click(target_name, hold_seconds=None):
    press_seconds = MOUSE_HOLD_SECONDS if hold_seconds is None else hold_seconds
    down, up = 0, 0
    if target_name == 'left':
        down, up = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
    elif target_name == 'right':
        down, up = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
    elif target_name == 'middle':
        down, up = MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP
    if down == 0:
        return
    down_input = INPUT(
        type=INPUT_MOUSE,
        union=INPUTUNION(mi=MOUSEINPUT(0, 0, 0, down, 0, 0))
    )
    up_input = INPUT(
        type=INPUT_MOUSE,
        union=INPUTUNION(mi=MOUSEINPUT(0, 0, 0, up, 0, 0))
    )
    down_inputs = (INPUT * 1)(down_input)
    up_inputs = (INPUT * 1)(up_input)
    down_ok = user32.SendInput(1, down_inputs, ctypes.sizeof(INPUT)) == 1
    time.sleep(press_seconds)
    up_ok = user32.SendInput(1, up_inputs, ctypes.sizeof(INPUT)) == 1
    if down_ok and up_ok:
        return True
    user32.mouse_event(down, 0, 0, 0, 0)
    time.sleep(press_seconds)
    user32.mouse_event(up, 0, 0, 0, 0)
    return _postmessage_mouse(target_name, press_seconds)

class HardwareInjector:
    def __init__(self):
        self._ready = False
        self._lock = threading.Lock()
        self.last_error = ""

    def available(self):
        return hw_interception is not None

    def ensure_ready(self):
        if not self.available():
            self.last_error = "未安装 interception-python 依赖"
            return False
        with self._lock:
            if self._ready:
                return True
            try:
                hw_interception.auto_capture_devices()
                self._ready = True
                self.last_error = ""
                return True
            except Exception as e:
                raw = str(e).strip()
                lower = raw.lower()
                if ("driver" in lower and "install" in lower) or "handle and event must be valid" in lower:
                    self.last_error = "未安装 Interception 驱动，请以管理员运行 install-interception.exe /install 后重启系统"
                else:
                    self.last_error = raw
                return False

    def send_keyboard_click(self, target_name, hold_seconds):
        if not self.ensure_ready():
            return False
        try:
            hw_interception.key_down(target_name, delay=0)
            time.sleep(max(0.001, hold_seconds))
            hw_interception.key_up(target_name, delay=0)
            self.last_error = ""
            return True
        except Exception as e:
            self.last_error = str(e)
            return False

    def send_mouse_click(self, target_name, hold_seconds):
        if not self.ensure_ready():
            return False
        try:
            hw_interception.mouse_down(target_name, delay=0)
            time.sleep(max(0.001, hold_seconds))
            hw_interception.mouse_up(target_name, delay=0)
            self.last_error = ""
            return True
        except Exception as e:
            self.last_error = str(e)
            return False

# --- Core Classes ---

class ClickTask:
    def __init__(self, task_id, target_name, interval_ms, mode, parent_engine):
        self.task_id = task_id
        self.target_name = target_name
        self.vk_code = get_vk_from_name(target_name)
        self.interval = max(0.001, interval_ms / 1000.0)
        self.mode = mode
        self.engine = parent_engine
        self.key_hold_seconds = max(0.003, min(0.03, self.interval * 0.45))
        self.mouse_hold_seconds = max(0.002, min(0.012, self.interval * 0.3))
        
        self.running = False
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.last_toggle_time = 0
        self.toggle_press_armed = False
        self.toggle_press_started_at = 0.0
        self.toggle_wait_release = False
        self._state_lock = threading.Lock()

    def start(self):
        with self._state_lock:
            if self.thread and self.thread.is_alive():
                return
            self.stop_event.clear()
        if self.engine.mutex_mode:
            self.engine.stop_all_except(self.task_id)
        worker = threading.Thread(target=self._run_loop)
        worker.daemon = True
        with self._state_lock:
            self.thread = worker
            self.running = True
        worker.start()

    def stop(self):
        with self._state_lock:
            worker = self.thread
            self.stop_event.set()
        if worker and worker.is_alive():
            worker.join(timeout=1.0)
        with self._state_lock:
            self.running = bool(self.thread and self.thread.is_alive())

    def is_running(self):
        with self._state_lock:
            return bool(self.thread and self.thread.is_alive())

    def _run_loop(self):
        next_time = time.perf_counter()
        try:
            while not self.stop_event.is_set():
                self._perform_click()
                next_time += self.interval
                sleep_time = next_time - time.perf_counter()
                if sleep_time > 0:
                    if self.stop_event.wait(sleep_time):
                        break
                else:
                    next_time = time.perf_counter()
        finally:
            with self._state_lock:
                if self.thread is threading.current_thread():
                    self.thread = None
                self.running = False
                self.stop_event.set()

    def _perform_click(self):
        self.engine.perform_click(
            self.target_name,
            self.vk_code,
            self.mouse_hold_seconds,
            self.key_hold_seconds,
            self.mode
        )

class HookThread(threading.Thread):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.hook_id = None
        self.daemon = True
        self.loop_running = False
        self.active = False # Manual start/stop flag
        self._hook_proc_ref = None # Keep reference to prevent GC

    def set_active(self, active: bool):
        self.active = active
        # If we are activating, we need to ensure the hook is installed.
        # But hook installation must happen in the thread that runs the message loop.
        # So we can't just call InstallHook here if the thread is already running a loop.
        # Actually, standard Windows Hooks are global but need a message loop.
        # The best way to "Stop" is just to ignore events in the callback, 
        # or PostThreadMessage to tell the loop to unhook.
        # For simplicity: We will just ignore events in the callback if active is False.

    def run(self):
        # This thread runs the message loop for the hook
        def hook_proc(nCode, wParam, lParam):
            if self.active and nCode >= 0:
                kb_struct = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                is_injected = kb_struct.flags & LLKHF_INJECTED
                
                if not is_injected:
                    is_down = (wParam == WM_KEYDOWN or wParam == WM_SYSKEYDOWN)
                    self.callback(kb_struct.vkCode, is_down)

            return user32.CallNextHookEx(self.hook_id, nCode, wParam, lParam)

        # Keep reference alive!
        self._hook_proc_ref = HOOKRPROC(hook_proc)

        h_mod = kernel32.GetModuleHandleW(None)
        self.hook_id = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._hook_proc_ref, h_mod, 0)
        
        if not self.hook_id:
            print(f"Failed to install hook. Error: {ctypes.GetLastError()}")
            return

        self.loop_running = True
        self.active = True # Auto-start active by default, or let controller decide?
        
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        
        if self.hook_id:
            user32.UnhookWindowsHookEx(self.hook_id)
        self.loop_running = False

    def stop(self):
        # We can't easily stop the GetMessage loop from another thread without PostThreadMessage.
        # But since it's a daemon thread, it will die with the app.
        pass

class EngineController:
    def __init__(self):
        self.tasks: Dict[str, ClickTask] = {}
        self.mutex_mode = False
        self._tasks_lock = threading.RLock()
        self._input_mode_lock = threading.Lock()
        self._injection_mode = "auto"
        self._injection_state = "系统模拟"
        self._hardware = HardwareInjector()
        self._suppress_until: Dict[int, float] = {}
        self.hook_thread = HookThread(self._on_key_event)
        self.hook_thread.start()
        self._poll_stop_event = threading.Event()
        self._key_state_cache: Dict[int, bool] = {}
        self._poll_thread = threading.Thread(target=self._poll_key_states_loop, daemon=True)
        self._poll_thread.start()

    def set_mutex_mode(self, enabled: bool):
        self.mutex_mode = enabled

    def set_hook_active(self, active: bool):
        self.hook_thread.set_active(active)

    def is_hook_active(self):
        return self.hook_thread.active

    def set_injection_mode(self, mode: str):
        normalized = mode if mode in {"auto", "winapi", "hardware"} else "auto"
        with self._input_mode_lock:
            self._injection_mode = normalized

    def get_injection_mode(self):
        with self._input_mode_lock:
            return self._injection_mode

    def get_injection_state(self):
        with self._input_mode_lock:
            return self._injection_state

    def _set_injection_state(self, value: str):
        with self._input_mode_lock:
            self._injection_state = value

    def _suppress_key(self, vk: int, duration_s: float = 0.01):
        if vk:
            bounded = min(0.02, max(0.003, duration_s))
            self._suppress_until[vk] = time.perf_counter() + bounded

    def _is_suppressed(self, vk: int) -> bool:
        until = self._suppress_until.get(vk)
        if until is None:
            return False
        now = time.perf_counter()
        if now >= until:
            self._suppress_until.pop(vk, None)
            return False
        return True

    def perform_click(self, target_name, vk_code, mouse_hold_seconds, key_hold_seconds, task_mode):
        injection_mode = self.get_injection_mode()
        is_mouse = target_name in ['left', 'right', 'middle']
        if injection_mode in {"auto", "hardware"}:
            hw_ok = self._hardware.send_mouse_click(target_name, mouse_hold_seconds) if is_mouse else self._hardware.send_keyboard_click(target_name, key_hold_seconds)
            if hw_ok:
                self._set_injection_state("硬件驱动")
                return
            if injection_mode == "hardware":
                self._set_injection_state(f"硬件失败: {self._hardware.last_error}")
                return
        if is_mouse:
            ok = send_mouse_click(target_name, mouse_hold_seconds)
        elif vk_code != 0:
            ok = send_keyboard_click(vk_code, target_name, key_hold_seconds)
        else:
            ok = False
        if ok:
            self._set_injection_state("系统模拟")
        else:
            fallback_msg = self._hardware.last_error if injection_mode in {"auto", "hardware"} else "无可用注入路径"
            self._set_injection_state(f"发送失败: {fallback_msg}")

    def add_task(self, task_id, target_name, interval_ms, mode):
        with self._tasks_lock:
            old_task = self.tasks.get(task_id)
            if old_task:
                old_task.stop()
            self.tasks[task_id] = ClickTask(task_id, target_name, interval_ms, mode, self)

    def remove_task(self, task_id):
        with self._tasks_lock:
            task = self.tasks.pop(task_id, None)
        if task:
            task.stop()

    def stop_all(self):
        with self._tasks_lock:
            task_list = list(self.tasks.values())
        for task in task_list:
            task.stop()

    def stop_all_except(self, keep_task_id):
        with self._tasks_lock:
            task_items = list(self.tasks.items())
        for tid, task in task_items:
            if tid != keep_task_id:
                task.stop()
    
    def get_task_status(self, task_id):
        with self._tasks_lock:
            task = self.tasks.get(task_id)
        if task:
            return task.is_running()
        return False

    def _on_key_event(self, vk_code, is_down, source_poll=False):
        if self._is_suppressed(vk_code):
            return
        with self._tasks_lock:
            relevant_tasks = [t for t in self.tasks.values() if t.vk_code == vk_code]
        for task in relevant_tasks:
            if task.mode == 'hold':
                if is_down:
                    if not task.is_running():
                        task.start()
                else:
                    if task.is_running():
                        task.stop()
            elif task.mode == 'toggle':
                now_perf = time.perf_counter()
                if task.toggle_wait_release:
                    if not is_down:
                        task.toggle_wait_release = False
                    continue
                if task.is_running() and source_poll:
                    if is_down:
                        if not task.toggle_press_armed:
                            task.toggle_press_armed = True
                            task.toggle_press_started_at = now_perf
                        elif now_perf - task.toggle_press_started_at >= TOGGLE_STOP_HOLD_SECONDS:
                            now = time.time()
                            if now - task.last_toggle_time > 0.08:
                                task.stop()
                                task.last_toggle_time = now
                                task.toggle_wait_release = True
                            task.toggle_press_armed = False
                    else:
                        task.toggle_press_armed = False
                    continue
                if is_down:
                    if not task.toggle_press_armed:
                        task.toggle_press_armed = True
                        task.toggle_press_started_at = now_perf
                else:
                    if not task.toggle_press_armed:
                        continue
                    press_duration = now_perf - task.toggle_press_started_at
                    task.toggle_press_armed = False
                    if press_duration < TOGGLE_MIN_PRESS_SECONDS:
                        continue
                    now = time.time()
                    if now - task.last_toggle_time > 0.12:
                        if task.is_running():
                            task.stop()
                        else:
                            task.start()
                        task.last_toggle_time = now

    def _poll_key_states_loop(self):
        while not self._poll_stop_event.is_set():
            if not self.hook_thread.active:
                self._poll_stop_event.wait(0.01)
                continue
            with self._tasks_lock:
                vk_codes = {task.vk_code for task in self.tasks.values() if task.vk_code}
            stale_keys = [vk for vk in self._key_state_cache if vk not in vk_codes]
            for vk in stale_keys:
                self._key_state_cache.pop(vk, None)
            for vk in vk_codes:
                is_down = bool(user32.GetAsyncKeyState(vk) & 0x8000)
                last_state = self._key_state_cache.get(vk)
                if last_state is None:
                    self._key_state_cache[vk] = is_down
                    continue
                if is_down != last_state:
                    self._key_state_cache[vk] = is_down
                    self._on_key_event(vk, is_down, source_poll=True)
            self._poll_stop_event.wait(0.005)
