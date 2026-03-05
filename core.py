import threading
import time
import ctypes
from ctypes import wintypes
import queue
from typing import Dict, Optional, Callable, List

# --- Windows API Constants & Structures ---

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

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

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
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

# --- Core Classes ---

class ClickTask:
    def __init__(self, task_id, target_name, interval_ms, mode, parent_engine):
        self.task_id = task_id
        self.target_name = target_name
        self.vk_code = get_vk_from_name(target_name)
        self.interval = max(0.001, interval_ms / 1000.0)
        self.mode = mode
        self.engine = parent_engine
        
        self.running = False
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.last_toggle_time = 0

    def start(self):
        if not self.running:
            if self.engine.mutex_mode:
                self.engine.stop_all_except(self.task_id)
            
            self.running = True
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._run_loop)
            self.thread.daemon = True
            self.thread.start()

    def stop(self):
        if self.running:
            self.running = False
            self.stop_event.set()
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=0.2)

    def is_running(self):
        return self.running

    def _run_loop(self):
        next_time = time.time()
        while not self.stop_event.is_set():
            self._perform_click()
            next_time += self.interval
            sleep_time = next_time - time.time()
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                next_time = time.time()

    def _perform_click(self):
        if self.target_name in ['left', 'right', 'middle']:
            down, up = 0, 0
            if self.target_name == 'left':
                down, up = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
            elif self.target_name == 'right':
                down, up = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
            elif self.target_name == 'middle':
                down, up = MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP
            
            user32.mouse_event(down, 0, 0, 0, 0)
            user32.mouse_event(up, 0, 0, 0, 0)
        elif self.vk_code != 0:
            user32.keybd_event(self.vk_code, 0, 0, 0)
            user32.keybd_event(self.vk_code, 0, KEYEVENTF_KEYUP, 0)

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
        self.hook_thread = HookThread(self._on_key_event)
        self.hook_thread.start()

    def set_mutex_mode(self, enabled: bool):
        self.mutex_mode = enabled

    def set_hook_active(self, active: bool):
        self.hook_thread.set_active(active)

    def is_hook_active(self):
        return self.hook_thread.active

    def add_task(self, task_id, target_name, interval_ms, mode):
        if task_id in self.tasks:
            self.tasks[task_id].stop()
        task = ClickTask(task_id, target_name, interval_ms, mode, self)
        self.tasks[task_id] = task

    def remove_task(self, task_id):
        if task_id in self.tasks:
            self.tasks[task_id].stop()
            del self.tasks[task_id]

    def stop_all(self):
        for task in self.tasks.values():
            task.stop()

    def stop_all_except(self, keep_task_id):
        for tid, task in self.tasks.items():
            if tid != keep_task_id:
                task.stop()
    
    def get_task_status(self, task_id):
        if task_id in self.tasks:
            return self.tasks[task_id].is_running()
        return False

    def _on_key_event(self, vk_code, is_down):
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
                if is_down:
                    now = time.time()
                    if now - task.last_toggle_time > 0.2:
                        if task.is_running():
                            task.stop()
                        else:
                            task.start()
                        task.last_toggle_time = now
