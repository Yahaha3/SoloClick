import threading
import time
import ctypes
import struct
from ctypes import wintypes
import queue
from typing import Dict, Optional, Callable, List
try:
    import interception as hw_interception
    from interception.strokes import KeyStroke as HWKeyStroke
    from interception.constants import KeyFlag as HWKeyFlag
    from interception import _keycodes as hw_keycodes
except Exception:
    hw_interception = None
    HWKeyStroke = None
    HWKeyFlag = None
    hw_keycodes = None

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

LLKHF_LOWER_IL_INJECTED = 0x00000002
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
MAPVK_VSC_TO_VK_EX = 3
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
HW_INJECT_INFO_MARK = 0x5A

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
    def __init__(self, debug_callback=None):
        self._ready = False
        self._lock = threading.Lock()
        self.last_error = ""
        self._ctx = None
        self._keyboard_device = None
        self._debug_callback = debug_callback

    def _debug(self, message: str):
        if self._debug_callback:
            self._debug_callback(message)

    def available(self):
        return hw_interception is not None and HWKeyStroke is not None and HWKeyFlag is not None and hw_keycodes is not None

    def _pick_keyboard_device(self):
        if not self._ctx:
            return None
        for i in range(10):
            try:
                if self._ctx.devices[i].get_HWID() is not None:
                    return i
            except Exception:
                continue
        return 1

    def ensure_ready(self):
        if not self.available():
            self.last_error = "未安装 interception-python 依赖"
            return False
        with self._lock:
            if self._ready:
                return True
            try:
                self._ctx = hw_interception.Interception()
                if not self._ctx.valid:
                    raise RuntimeError("Interception 驱动未就绪")
                self._keyboard_device = self._pick_keyboard_device()
                self._ready = True
                self.last_error = ""
                self._debug(f"硬件注入就绪: keyboard_device={self._keyboard_device}")
                return True
            except Exception as e:
                raw = str(e).strip()
                lower = raw.lower()
                if ("driver" in lower and "install" in lower) or "handle and event must be valid" in lower:
                    self.last_error = "未安装 Interception 驱动，请以管理员运行 install-interception.exe /install 后重启系统"
                else:
                    self.last_error = raw
                self._debug(f"硬件注入初始化失败: {self.last_error}")
                return False

    def send_keyboard_click(self, target_name, hold_seconds):
        if not self.ensure_ready():
            return False
        try:
            key_data = hw_keycodes.get_key_information(target_name)
            down_flags = int(HWKeyFlag.KEY_DOWN)
            up_flags = int(HWKeyFlag.KEY_UP)
            if key_data.is_extended:
                down_flags |= int(HWKeyFlag.KEY_E0)
                up_flags |= int(HWKeyFlag.KEY_E0)
            down = HWKeyStroke(key_data.scan_code, down_flags)
            up = HWKeyStroke(key_data.scan_code, up_flags)
            down.information = HW_INJECT_INFO_MARK
            up.information = HW_INJECT_INFO_MARK
            self._ctx.send(self._keyboard_device, down)
            time.sleep(max(0.001, hold_seconds))
            self._ctx.send(self._keyboard_device, up)
            self.last_error = ""
            self._debug(f"硬件注入键盘: key={target_name} scan={key_data.scan_code} mark={HW_INJECT_INFO_MARK}")
            return True
        except Exception as e:
            self.last_error = str(e)
            self._debug(f"硬件注入键盘失败: key={target_name} err={self.last_error}")
            return False

    def send_mouse_click(self, target_name, hold_seconds):
        if not self.ensure_ready():
            return False
        try:
            hw_interception.mouse_down(target_name, delay=0)
            time.sleep(max(0.001, hold_seconds))
            hw_interception.mouse_up(target_name, delay=0)
            self.last_error = ""
            self._debug(f"硬件注入鼠标: btn={target_name}")
            return True
        except Exception as e:
            self.last_error = str(e)
            self._debug(f"硬件注入鼠标失败: btn={target_name} err={self.last_error}")
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
                is_down = (wParam == WM_KEYDOWN or wParam == WM_SYSKEYDOWN)
                self.callback(
                    kb_struct.vkCode,
                    is_down,
                    source_hook=True,
                    hook_injected=bool(kb_struct.flags & LLKHF_INJECTED),
                    hook_lower_il=bool(kb_struct.flags & LLKHF_LOWER_IL_INJECTED),
                    hook_scan_code=int(kb_struct.scanCode),
                    hook_flags=int(kb_struct.flags),
                )

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

class DriverTriggerThread(threading.Thread):
    def __init__(self, callback, debug_callback=None):
        super().__init__(daemon=True)
        self.callback = callback
        self.active = True
        self.ready = False
        self.error = ""
        self._ctx = None
        self._debug_callback = debug_callback

    def _debug(self, message: str):
        if self._debug_callback:
            self._debug_callback(message)

    def set_active(self, active: bool):
        self.active = active

    def run(self):
        if hw_interception is None or HWKeyStroke is None or HWKeyFlag is None:
            self.error = "驱动触发依赖不可用"
            self._debug(self.error)
            return
        try:
            self._ctx = hw_interception.Interception()
            if not self._ctx.valid:
                self.error = "Interception 触发上下文不可用"
                self._debug(self.error)
                return
            key_filter = int(HWKeyFlag.KEY_UP) | (int(HWKeyFlag.KEY_UP) << 1)
            self._ctx.set_filter(self._ctx.is_keyboard, key_filter)
            self.ready = True
            self._debug("驱动触发线程已就绪")
            while True:
                device = self._ctx.await_input(50)
                if device is None:
                    continue
                device_obj = self._ctx.devices[device]
                io_result = device_obj._receive()
                raw_data = io_result.data
                if raw_data is None:
                    continue
                if device_obj.is_keyboard:
                    try:
                        unit_id, scan_code, flags, reserved, info = struct.unpack(HWKeyStroke.format, raw_data)
                    except Exception:
                        continue
                    stroke = HWKeyStroke(scan_code, flags)
                    stroke._unit_id = unit_id
                    stroke._reserved = reserved
                    stroke.information = info
                    info_mark = int(info) & 0xFF
                    is_down = (int(flags) & int(HWKeyFlag.KEY_UP)) == 0
                    vk_code = user32.MapVirtualKeyW(int(stroke.code), MAPVK_VSC_TO_VK_EX)
                    self._debug(f"驱动触发事件: dev={device} scan={int(stroke.code)} vk={vk_code} down={is_down} mark={info_mark}")
                    if self.active:
                        if vk_code:
                            self.callback(vk_code, is_down, source_driver=True, driver_mark=info_mark)
                    device_obj.send(stroke)
                else:
                    stroke = device_obj._parser.parse(raw_data)
                    device_obj.send(stroke)
        except Exception as e:
            self.error = str(e)
            self.ready = False
            self._debug(f"驱动触发线程异常: {self.error}")

class EngineController:
    def __init__(self):
        self.tasks: Dict[str, ClickTask] = {}
        self.mutex_mode = False
        self._tasks_lock = threading.RLock()
        self._input_mode_lock = threading.Lock()
        self._injection_mode = "auto"
        self._injection_state = "系统模拟"
        self._debug_state = "调试: 初始化中"
        self._driver_release_total = 0
        self._hardware = HardwareInjector(self._set_debug_state)
        self._suppress_until: Dict[int, float] = {}
        self._driver_seen_noninject_ts = 0.0
        self._driver_seen_inject_ts = 0.0
        self._input_stats_lock = threading.Lock()
        self._input_stats = {
            "hook_physical": 0,
            "hook_injected": 0,
            "driver_physical": 0,
            "driver_self_injected": 0,
            "poll_input": 0,
            "ignored_non_driver": 0,
        }
        self.hook_thread = HookThread(self._on_key_event)
        self.hook_thread.start()
        self.driver_trigger_thread = DriverTriggerThread(self._on_key_event, self._set_debug_state)
        self.driver_trigger_thread.start()
        self._poll_stop_event = threading.Event()
        self._key_state_cache: Dict[int, bool] = {}
        self._poll_thread = threading.Thread(target=self._poll_key_states_loop, daemon=True)
        self._poll_thread.start()

    def set_mutex_mode(self, enabled: bool):
        self.mutex_mode = enabled

    def set_hook_active(self, active: bool):
        self.hook_thread.set_active(active)
        if self.driver_trigger_thread:
            self.driver_trigger_thread.set_active(active)

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

    def _set_debug_state(self, value: str):
        with self._input_mode_lock:
            self._debug_state = value

    def get_debug_state(self):
        with self._input_mode_lock:
            return self._debug_state

    def _bump_driver_release_total(self):
        with self._input_mode_lock:
            self._driver_release_total += 1

    def get_driver_release_debug(self):
        with self._input_mode_lock:
            return f"D物理弹起总次数: {self._driver_release_total}"

    def _bump_input_stat(self, key: str):
        with self._input_stats_lock:
            if key in self._input_stats:
                self._input_stats[key] += 1

    def _format_input_stats(self):
        with self._input_stats_lock:
            hook_physical = self._input_stats["hook_physical"]
            hook_injected = self._input_stats["hook_injected"]
            driver_physical = self._input_stats["driver_physical"]
            driver_self_injected = self._input_stats["driver_self_injected"]
            poll_input = self._input_stats["poll_input"]
            ignored_non_driver = self._input_stats["ignored_non_driver"]
        return f"统计 H物理={hook_physical}, H注入={hook_injected}, D物理={driver_physical}, D自注入={driver_self_injected}, P={poll_input}, 忽略={ignored_non_driver}"

    def _use_driver_trigger(self):
        mode = self.get_injection_mode()
        if mode not in {"hardware", "auto"}:
            return False
        if not self.driver_trigger_thread or not self.driver_trigger_thread.ready:
            return False
        now = time.perf_counter()
        if self._driver_seen_noninject_ts and now - self._driver_seen_noninject_ts < 1.5:
            return True
        if self._driver_seen_inject_ts and now - self._driver_seen_inject_ts < 1.5:
            self._set_debug_state("驱动触发异常: 仅检测到自注入，已回退到轮询")
        return False

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
                if not is_mouse:
                    self._driver_seen_inject_ts = time.perf_counter()
                    self._bump_input_stat("driver_self_injected")
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

    def _on_key_event(
        self,
        vk_code,
        is_down,
        source_poll=False,
        source_driver=False,
        source_hook=False,
        driver_mark=None,
        hook_injected=False,
        hook_lower_il=False,
        hook_scan_code=None,
        hook_flags=0,
    ):
        if source_hook and hook_injected:
            self._bump_input_stat("hook_injected")
            self._set_debug_state(
                f"Hook过滤: 注入 vk={vk_code} scan={hook_scan_code} lower_il={int(bool(hook_lower_il))} flags=0x{int(hook_flags):02X} | {self._format_input_stats()}"
            )
            return
        if source_driver:
            now = time.perf_counter()
            if driver_mark == HW_INJECT_INFO_MARK:
                self._driver_seen_inject_ts = now
                self._bump_input_stat("driver_self_injected")
                self._set_debug_state(f"驱动过滤: 自注入 vk={vk_code} mark={driver_mark} | {self._format_input_stats()}")
                return
            else:
                self._driver_seen_noninject_ts = now
                self._bump_input_stat("driver_physical")
        if self._use_driver_trigger() and not source_driver:
            self._bump_input_stat("ignored_non_driver")
            src = "poll" if source_poll else ("hook" if source_hook else "unknown")
            self._set_debug_state(f"触发忽略: 非驱动源 src={src} vk={vk_code} down={is_down} | {self._format_input_stats()}")
            return
        if source_poll:
            self._bump_input_stat("poll_input")
        elif source_hook:
            self._bump_input_stat("hook_physical")
        if self._is_suppressed(vk_code):
            self._set_debug_state(f"触发忽略: 抑制窗口 vk={vk_code}")
            return
        with self._tasks_lock:
            relevant_tasks = [t for t in self.tasks.values() if t.vk_code == vk_code]
        if source_driver and not is_down:
            self._bump_driver_release_total()
        if not relevant_tasks:
            self._set_debug_state(f"输入识别: 未匹配任务 vk={vk_code} down={is_down} | {self._format_input_stats()}")
            return
        src = "driver" if source_driver else ("poll" if source_poll else ("hook" if source_hook else "unknown"))
        if source_driver:
            self._set_debug_state(f"触发输入: src={src} vk={vk_code} down={is_down} mark={driver_mark} tasks={len(relevant_tasks)} | {self._format_input_stats()}")
        else:
            self._set_debug_state(f"触发输入: src={src} vk={vk_code} down={is_down} tasks={len(relevant_tasks)} | {self._format_input_stats()}")
        for task in relevant_tasks:
            if task.mode == 'hold':
                if is_down:
                    if not task.is_running():
                        task.start()
                        self._set_debug_state(f"任务启动: mode=hold key={task.target_name}")
                else:
                    if task.is_running():
                        task.stop()
                        self._set_debug_state(f"任务停止: mode=hold key={task.target_name}")
            elif task.mode == 'toggle':
                now_perf = time.perf_counter()
                if source_driver:
                    if is_down:
                        continue
                    now = time.time()
                    if now - task.last_toggle_time <= 0.06:
                        continue
                    if task.is_running():
                        task.stop()
                        self._set_debug_state(f"任务停止: mode=toggle key={task.target_name} by_driver_release")
                    else:
                        task.start()
                        self._set_debug_state(f"任务启动: mode=toggle key={task.target_name} by_driver_release")
                    task.last_toggle_time = now
                    continue
                stop_by_release_source = source_poll or source_driver
                if task.toggle_wait_release:
                    if not is_down:
                        task.toggle_wait_release = False
                    continue
                if task.is_running() and not stop_by_release_source:
                    continue
                if task.is_running() and stop_by_release_source:
                    if is_down:
                        if not task.toggle_press_armed:
                            task.toggle_press_armed = True
                            task.toggle_press_started_at = now_perf
                    else:
                        if not task.toggle_press_armed:
                            continue
                        press_duration = now_perf - task.toggle_press_started_at
                        task.toggle_press_armed = False
                        if press_duration < TOGGLE_STOP_HOLD_SECONDS:
                            continue
                        now = time.time()
                        if now - task.last_toggle_time > 0.08:
                            task.stop()
                            task.last_toggle_time = now
                            self._set_debug_state(f"任务停止: mode=toggle key={task.target_name} by_hold={press_duration:.3f}s")
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
                            self._set_debug_state(f"任务停止: mode=toggle key={task.target_name} press={press_duration:.3f}s")
                        else:
                            task.start()
                            self._set_debug_state(f"任务启动: mode=toggle key={task.target_name} press={press_duration:.3f}s")
                        task.last_toggle_time = now

    def _poll_key_states_loop(self):
        while not self._poll_stop_event.is_set():
            if not self.hook_thread.active:
                self._poll_stop_event.wait(0.01)
                continue
            if self._use_driver_trigger():
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
