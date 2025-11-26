# -*- coding: utf-8 -*-
from __future__ import annotations
import os
import sys
import time
import hashlib
import platform
import subprocess
import re
import io
import base64
import winreg  # Thư viện thao tác Registry
import ctypes  # Thư viện thao tác Window API
import threading # Để chạy popup không làm đơ chương trình chính
import tkinter as tk # Thư viện vẽ giao diện
from tkinter import font as tkfont # Để chỉnh font chi tiết

from dotenv import load_dotenv
import pyperclip
import psutil
from openai import OpenAI
from PIL import Image, ImageGrab, ImageTk # Cần Pillow để xử lý ảnh

# ==============================
#  OS DETECTION
# ==============================

SYSTEM = platform.system()
IS_WINDOWS = SYSTEM == "Windows"
IS_MAC = SYSTEM == "Darwin"

if IS_WINDOWS:
    try:
        import win32gui
        import win32process
        import win32con
    except ImportError:
        win32gui = None
        win32process = None
        win32con = None
else:
    win32gui = None
    win32process = None


# ==============================
#  GLOBAL CONFIG
# ==============================

APP_NAME = "DLP_Clipboard_Guard"
RUN_FLAG = True

# Tên file ảnh
BIG_ICON_FILENAME = "shield_icon.png"   # Ảnh 3D to ở giữa
SMALL_ICON_FILENAME = "defend_logo.png" # Ảnh logo nhỏ cạnh chữ Data Loss Prevention

# ==============================
#  WHITELIST IDE / EDITOR
# ==============================
ALLOWED_CODE_APPS_WIN = {
    "Code.exe", "code.exe", "devenv.exe", "idea64.exe", "pycharm64.exe",
    "clion64.exe", "phpstorm64.exe", "webstorm64.exe", "notepad++.exe", "sublime_text.exe"
}

ALLOWED_CODE_APPS_MAC = {
    "Visual Studio Code", "Code", "Electron", "PyCharm", "IntelliJ IDEA",
    "CLion", "PhpStorm", "WebStorm", "Sublime Text", "Xcode"
}


# ==============================
#  SYSTEM FUNCTIONS
# ==============================

def hide_console_window():
    """Ẩn cửa sổ Console ngay lập tức (Chỉ dùng cho Windows)."""
    if IS_WINDOWS:
        try:
            if win32gui:
                hwnd = win32gui.GetForegroundWindow()
                win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
            else:
                kernel32 = ctypes.WinDLL('kernel32')
                user32 = ctypes.WinDLL('user32')
                hwnd = kernel32.GetConsoleWindow()
                if hwnd:
                    user32.ShowWindow(hwnd, 0)  # 0 = SW_HIDE
        except Exception:
            pass

def add_to_startup():
    """Tự thêm chương trình vào Registry Run."""
    if not IS_WINDOWS: return
    try:
        exe_path = sys.executable
        if not getattr(sys, 'frozen', False):
            exe_path = f'"{sys.executable}" "{os.path.abspath(__file__)}"'
        else:
            exe_path = f'"{exe_path}"'

        key = winreg.HKEY_CURRENT_USER
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        
        with winreg.OpenKey(key, key_path, 0, winreg.KEY_ALL_ACCESS) as registry_key:
            try:
                existing_val, _ = winreg.QueryValueEx(registry_key, APP_NAME)
                if existing_val == exe_path: return 
            except FileNotFoundError: pass 
            winreg.SetValueEx(registry_key, APP_NAME, 0, winreg.REG_SZ, exe_path)
            print(f"✅ [Startup] Đã kích hoạt khởi động cùng Windows.")
    except Exception as e:
        print(f"⚠️ [Startup] Lỗi: {e}")

def remove_from_startup():
    """Xóa chương trình khỏi Registry Run."""
    if not IS_WINDOWS: return
    try:
        key = winreg.HKEY_CURRENT_USER
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(key, key_path, 0, winreg.KEY_ALL_ACCESS) as registry_key:
            try:
                winreg.DeleteValue(registry_key, APP_NAME)
                print(f"✅ [Uninstall] Đã gỡ bỏ khỏi Startup.")
                ctypes.windll.user32.MessageBoxW(0, f"Đã gỡ bỏ {APP_NAME} khỏi Startup!", "Thông báo", 0x40)
            except FileNotFoundError:
                ctypes.windll.user32.MessageBoxW(0, "Chương trình chưa có trong Startup.", "Thông báo", 0x40)
    except Exception as e:
        ctypes.windll.user32.MessageBoxW(0, f"Lỗi: {e}", "Lỗi", 0x10)

def get_active_app_name() -> str | None:
    if IS_WINDOWS and win32gui and win32process:
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd: return None
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            return psutil.Process(pid).name()
        except Exception:
            return None
    elif IS_MAC:
        try:
            script = 'tell application "System Events" to get name of first application process whose frontmost is true'
            return subprocess.check_output(["osascript", "-e", script]).decode("utf-8").strip()
        except Exception:
            return None
    return None

def is_active_app_allowed_for_code() -> bool:
    name = get_active_app_name()
    if not name: return False
    if IS_WINDOWS: return name in ALLOWED_CODE_APPS_WIN
    if IS_MAC: return name in ALLOWED_CODE_APPS_MAC
    return False


# ==============================
#  CUSTOM UI LOGIC (VẼ GIAO DIỆN)
# ==============================

def _run_popup_gui(title, message, big_icon_path, small_icon_path):
    """
    Hàm này sẽ vẽ cửa sổ thông báo Custom.
    """
    try:
        # --- CẤU HÌNH MÀU SẮC ---
        COLOR_BG_TOP = "#162036"    # Xanh tối (Header)
        COLOR_BG_BOT = "#1f1f1f"    # Đen xám (Body)
        COLOR_TEXT_H1 = "#ffffff"   # Màu chữ tiêu đề
        COLOR_TEXT_P = "#cccccc"    # Màu chữ nội dung
        
        # Nút Dismiss
        COLOR_BTN_BG = "#3a3a3a"    
        COLOR_BTN_HOVER = "#505050"
        COLOR_BTN_FG = "#ffffff"

        root = tk.Tk()
        root.overrideredirect(True) # Borderless
        root.attributes('-topmost', True) # Always on top
        
        # --- KÍCH THƯỚC ---
        w, h = 380, 300 
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        x_pos = screen_w - w - 20
        y_pos = screen_h - h - 60
        root.geometry(f"{w}x{h}+{x_pos}+{y_pos}")

        # --- FRAME TRÊN (HEADER XANH) ---
        frame_top = tk.Frame(root, bg=COLOR_BG_TOP, height=150)
        frame_top.pack(fill="x", side="top")
        frame_top.pack_propagate(False)

        # --- LOGO TO (Ở GIỮA VÙNG XANH) ---
        if os.path.exists(big_icon_path):
            try:
                pil_img = Image.open(big_icon_path)
                pil_img.thumbnail((110, 110), Image.Resampling.LANCZOS)
                tk_img = ImageTk.PhotoImage(pil_img)
                
                lbl_img = tk.Label(frame_top, image=tk_img, bg=COLOR_BG_TOP, bd=0)
                lbl_img.image = tk_img 
                lbl_img.place(relx=0.5, rely=0.5, anchor="center")
            except Exception: pass
        
        # Nút đóng (X)
        btn_close = tk.Label(frame_top, text="✕", bg=COLOR_BG_TOP, fg="#aaaaaa", font=("Arial", 12), cursor="hand2")
        btn_close.place(relx=0.95, rely=0.1, anchor="ne")
        btn_close.bind("<Button-1>", lambda e: root.destroy())

        # --- FRAME DƯỚI (BODY ĐEN) ---
        frame_bot = tk.Frame(root, bg=COLOR_BG_BOT)
        frame_bot.pack(fill="both", expand=True, side="bottom")

        # --- HEADER NHỎ + ICON NHỎ (Data Loss Prevention) ---
        # Tạo Frame con để chứa icon nhỏ và text nằm ngang hàng
        frame_header_small = tk.Frame(frame_bot, bg=COLOR_BG_BOT)
        frame_header_small.pack(anchor="w", padx=20, pady=(12, 0))

        # Xử lý icon nhỏ (defend_logo.png)
        if os.path.exists(small_icon_path):
            try:
                pil_small = Image.open(small_icon_path)
                # Resize về khoảng 16x16 pixel
                pil_small.thumbnail((18, 18), Image.Resampling.LANCZOS)
                tk_small_icon = ImageTk.PhotoImage(pil_small)
                
                # Label chứa ảnh
                lbl_small_icon = tk.Label(frame_header_small, image=tk_small_icon, bg=COLOR_BG_BOT, bd=0)
                lbl_small_icon.image = tk_small_icon
                lbl_small_icon.pack(side="left", padx=(0, 5)) # Cách text 5px
            except: pass
        else:
            # Fallback nếu không có ảnh thì dùng emoji
            tk.Label(frame_header_small, text="🛡️", bg=COLOR_BG_BOT, fg=COLOR_TEXT_H1).pack(side="left", padx=(0,5))

        # Text "Data Loss Prevention"
        font_header = tkfont.Font(family="Segoe UI", size=9)
        lbl_head_text = tk.Label(frame_header_small, text="Data Loss Prevention", bg=COLOR_BG_BOT, fg=COLOR_TEXT_H1, font=font_header)
        lbl_head_text.pack(side="left")

        # Tiêu đề chính (Bold)
        font_title = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        lbl_title = tk.Label(frame_bot, text=title, bg=COLOR_BG_BOT, fg=COLOR_TEXT_H1, font=font_title)
        lbl_title.pack(anchor="w", padx=20, pady=(2, 0))

        # Nội dung
        font_msg = tkfont.Font(family="Segoe UI", size=9)
        lbl_msg = tk.Label(frame_bot, text=message, bg=COLOR_BG_BOT, fg=COLOR_TEXT_P, font=font_msg, wraplength=340, justify="left")
        lbl_msg.pack(anchor="w", padx=20, pady=(4, 15))

        # --- NÚT DISMISS ---
        def on_enter(e): btn_dismiss.config(bg=COLOR_BTN_HOVER)
        def on_leave(e): btn_dismiss.config(bg=COLOR_BTN_BG)
        
        btn_dismiss = tk.Label(frame_bot, text="Dismiss", bg=COLOR_BTN_BG, fg=COLOR_BTN_FG, 
                               font=("Segoe UI", 10, "bold"), cursor="hand2")
        
        btn_dismiss.pack(fill="x", padx=20, pady=(0, 20), ipady=12)
        
        btn_dismiss.bind("<Button-1>", lambda e: root.destroy())
        btn_dismiss.bind("<Enter>", on_enter)
        btn_dismiss.bind("<Leave>", on_leave)

        # Tự đóng sau 8 giây
        root.after(8000, root.destroy)
        
        root.mainloop()
    except Exception:
        pass

def show_custom_alert(title, message, big_icon, small_icon):
    """Gọi GUI trong một luồng (Thread) riêng."""
    t = threading.Thread(target=_run_popup_gui, args=(title, message, big_icon, small_icon))
    t.daemon = True 
    t.start()


# ==============================
#  LLM & CLIPBOARD LOGIC
# ==============================

TEXT_PROMPT = """
You are a clipboard content classification expert for TEXT.
CRITICAL RULES:
1) If text contains ANY source code -> 'source code'.
2) If normal prose -> 'This is normal text.'
3) If meaningless -> 'No meaningful content.'
Always respond with exactly one sentence enclosed in [CONCLUSION: ...].
"""

IMAGE_PROMPT = """
You are an image analysis expert.
CRITICAL RULES:
1) If image contains ANY source code -> 'source code'.
2) If normal text -> 'This is normal text.'
3) If no text -> 'No meaningful content.'
Always respond with exactly one sentence enclosed in [CONCLUSION: ...].
"""

def smart_truncate(content: str, max_length: int = 2000) -> str:
    if len(content) <= max_length: return content
    part_size = max_length // 3
    return f"{content[:part_size]}\n\n[...]\n\n{content[len(content)//2 : len(content)//2+part_size]}\n\n[...]\n\n{content[-part_size:]}"

def image_to_data_url(img: Image.Image) -> str:
    with io.BytesIO() as buf:
        if img.mode not in ("RGB", "RGBA"): img = img.convert("RGB")
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"

def call_llm(client: OpenAI, model: str, content: str | Image.Image) -> str:
    if isinstance(content, str):
        messages = [{"role": "system", "content": TEXT_PROMPT + " [CONCLUSION: ...]."}, {"role": "user", "content": smart_truncate(content)}]
    else:
        messages = [
            {"role": "system", "content": IMAGE_PROMPT + " [CONCLUSION: ...]."},
            {"role": "user", "content": [{"type": "text", "text": "Classify content."}, {"type": "image_url", "image_url": {"url": image_to_data_url(content)}}]}
        ]
    res = client.chat.completions.create(model=model, messages=messages, max_tokens=32, temperature=0.0)
    out = (res.choices[0].message.content or "").strip()
    m = re.findall(r"\[CONCLUSION[:：](.*?)\]", out, flags=re.IGNORECASE)
    return (m[0].strip() if m else out).strip()

def parse_classification(raw: str) -> str:
    raw = raw.lower()
    if "this is normal text" in raw or "no meaningful content" in raw: return "TEXT"
    return "CODE"

def hash_data(data: str | Image.Image) -> str:
    if isinstance(data, str): return hashlib.sha256(data.encode("utf-8", "ignore")).hexdigest()
    with io.BytesIO() as buf:
        if data.mode not in ("RGB", "RGBA"): data = data.convert("RGB")
        data.save(buf, "PNG")
        return hashlib.sha256(buf.getvalue()).hexdigest()

def get_clipboard():
    try:
        text = pyperclip.paste()
        if text and text.strip(): return "text", text.strip()
    except: pass
    try:
        img = ImageGrab.grabclipboard()
        if isinstance(img, Image.Image): return "image", img
    except: pass
    return "empty", None

def set_clipboard(type_, data):
    try:
        if type_ == "text": pyperclip.copy(data)
        elif type_ == "image" and IS_WINDOWS:
            output = io.BytesIO()
            data.convert("RGB").save(output, "BMP")
            d = output.getvalue()[14:]
            output.close()
            import win32clipboard
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, d)
            win32clipboard.CloseClipboard()
            return True
    except: return False
    return False

# ==============================
#  MAIN LOGIC LOOP
# ==============================

def main_loop(base_url, api_key, model):
    client = OpenAI(base_url=base_url, api_key=api_key)
    
    # === CẤU HÌNH NỘI DUNG THÔNG BÁO ===
    ALERT_HEADER = "Your organization's policy" # Dòng chữ to đậm
    ALERT_BODY = "Copying content containing Source Code is not allowed." # Nội dung bên dưới
    
    WARN_TXT = "" 
    LOCK_TXT = "" 
    WARN_HASH = "BLOCKED_CONTENT"
    
    cache = {}
    last_hash = None
    last_type = None
    last_in_ide = None
    
    # --- QUAN TRỌNG: Lấy đường dẫn icon đúng khi chạy EXE ---
    if getattr(sys, 'frozen', False):
        # Nếu chạy từ file EXE (đã build)
        # _MEIPASS là thư mục tạm mà PyInstaller bung nén file ra
        base_dir = sys._MEIPASS 
    else:
        # Nếu chạy script Python bình thường
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
    # Đường dẫn 2 file ảnh
    big_icon_abs = os.path.join(base_dir, BIG_ICON_FILENAME)
    small_icon_abs = os.path.join(base_dir, SMALL_ICON_FILENAME)

    # --- LOGIC ẨN CỬA SỔ ---
    is_frozen_exe = getattr(sys, 'frozen', False)
    if is_frozen_exe:
        print("🚀 DLP Guard (EXE Mode). Hiding console in 2 seconds...")
        time.sleep(2)
        hide_console_window()
    else:
        print(f"🔧 DLP Guard (Dev Mode). Icons: {BIG_ICON_FILENAME}, {SMALL_ICON_FILENAME}")

    while RUN_FLAG:
        try:
            ctype, cdata = get_clipboard()
            if ctype == "empty":
                time.sleep(0.1)
                continue

            curr_hash = hash_data(cdata)

            if curr_hash == last_hash or curr_hash == WARN_HASH:
                if last_in_ide and is_active_app_allowed_for_code():
                    time.sleep(0.1)
                    continue
                if curr_hash == WARN_HASH:
                    time.sleep(0.1)
                    continue

            in_ide = is_active_app_allowed_for_code()
            if in_ide:
                last_hash = curr_hash
                last_type = ctype
                last_in_ide = True
                time.sleep(0.1)
                continue
            
            last_in_ide = False
            
            if curr_hash in cache:
                if cache[curr_hash] == "TEXT":
                    last_hash = curr_hash
                    time.sleep(0.1)
                    continue
                else:
                    pyperclip.copy(WARN_TXT)
                    show_custom_alert(ALERT_HEADER, ALERT_BODY, big_icon_abs, small_icon_abs)
                    last_hash = WARN_HASH
                    continue

            orig_data = cdata
            orig_type = ctype
            orig_hash = curr_hash
            
            pyperclip.copy(LOCK_TXT)
            
            try:
                res = call_llm(client, model, orig_data)
                kind = parse_classification(res)
                cache[orig_hash] = kind
                
                if kind == "TEXT":
                    set_clipboard(orig_type, orig_data)
                    last_hash = orig_hash
                else:
                    pyperclip.copy(WARN_TXT)
                    last_hash = WARN_HASH
                    show_custom_alert(ALERT_HEADER, ALERT_BODY, big_icon_abs, small_icon_abs)
                    
            except Exception as e:
                set_clipboard(orig_type, orig_data)
                time.sleep(1)

            time.sleep(0.1)

        except Exception:
            time.sleep(1)

# ==============================
#  ENTRY POINT
# ==============================

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower() == "--remove":
        print("🛑 Đang thực hiện gỡ bỏ khởi động...")
        remove_from_startup()
        sys.exit(0)

    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
        if hasattr(sys, '_MEIPASS'):
             env_bundled = os.path.join(sys._MEIPASS, ".env")
             if os.path.exists(env_bundled):
                 load_dotenv(env_bundled)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    load_dotenv(os.path.join(base_path, ".env"))

    url = os.getenv("AZURE_INFERENCE_ENDPOINT")
    key = os.getenv("AZURE_INFERENCE_KEY")
    model = os.getenv("AZURE_INFERENCE_MODEL")

    if not url or not key:
        ctypes.windll.user32.MessageBoxW(0, "Missing .env configuration!", "DLP Error", 0x10)
        sys.exit(1)

    add_to_startup()
    main_loop(url, key, model)