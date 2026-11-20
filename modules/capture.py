"""屏幕/窗口捕获：枚举窗口、抓取画面、画面变化评分。

只依赖 ctypes + Pillow，无第三方库。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time
from dataclasses import dataclass

from PIL import Image, ImageChops, ImageGrab, ImageStat

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
dwmapi = ctypes.windll.dwmapi

DWMWA_EXTENDED_FRAME_BOUNDS = 9

# PrintWindow 标志：PW_RENDERFULLCONTENT 让 Chromium/Electron 窗口在被遮挡时也能截图
PW_RENDERFULLCONTENT = 0x00000002

_dpi_done = False


def make_dpi_aware() -> None:
    """声明进程 DPI 感知，保证 GetWindowRect 与屏幕抓取的坐标一致（物理像素）。"""
    global _dpi_done
    if _dpi_done:
        return
    try:
        # Windows 10 1703+：PER_MONITOR_AWARE_V2
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass
    _dpi_done = True


def dpi_scale() -> float:
    """当前主显示器缩放比例（1.0 = 100%）。"""
    try:
        dpi = user32.GetDpiForSystem()
        return dpi / 96.0
    except Exception:
        return 1.0


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    x: int
    y: int
    w: int
    h: int
    pid: int
    minimized: bool

    @property
    def rect(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.w, self.y + self.h)

    def label(self) -> str:
        t = self.title.strip() or "(无标题)"
        if len(t) > 80:
            t = t[:77] + "..."
        return f"{t}   [{self.w}x{self.h}]"


@dataclass(frozen=True)
class CaptureResult:
    image: Image.Image
    source: str  # 描述：窗口标题 / 全屏
    taken_at: float


def _rect_of(hwnd: int) -> tuple[int, int, int, int]:
    """窗口真实可见范围（去掉 Win10 的不可见阴影边框）。"""
    r = wt.RECT()
    try:
        hr = dwmapi.DwmGetWindowAttribute(
            wt.HWND(hwnd),
            ctypes.c_uint(DWMWA_EXTENDED_FRAME_BOUNDS),
            ctypes.byref(r),
            ctypes.sizeof(r),
        )
        if hr == 0 and (r.right - r.left) > 20 and (r.bottom - r.top) > 20:
            return (r.left, r.top, r.right, r.bottom)
    except Exception:
        pass
    if not user32.GetWindowRect(wt.HWND(hwnd), ctypes.byref(r)):
        return (0, 0, 0, 0)
    return (r.left, r.top, r.right, r.bottom)


def list_windows(include_own: bool = False, allow_untitled: bool = False) -> list[WindowInfo]:
    """列出所有可见、有标题、尺寸合理的顶层窗口（按标题排序）。"""
    make_dpi_aware()
    out: list[WindowInfo] = []
    own_pid = ctypes.windll.kernel32.GetCurrentProcessId()

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def _cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        title = buf.value.strip()
        if not title:
            return True
        l, t, r, b = _rect_of(hwnd)
        w, h = r - l, b - t
        if w < 120 or h < 80:
            return True
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == own_pid and not include_own:
            return True
        out.append(
            WindowInfo(
                hwnd=int(hwnd),
                title=title,
                x=l,
                y=t,
                w=w,
                h=h,
                pid=int(pid.value),
                minimized=bool(user32.IsIconic(hwnd)),
            )
        )
        return True

    user32.EnumWindows(_cb, 0)
    out.sort(key=lambda wi: wi.title.lower())
    return out


def _grab_screen(bbox: tuple[int, int, int, int]) -> Image.Image:
    return ImageGrab.grab(bbox=bbox, all_screens=True)


def _grab_printwindow(hwnd: int, w: int, h: int) -> Image.Image:
    """用 PrintWindow 抓窗口内容（窗口被遮挡时仍可用）。失败返回 1x1 空图。"""

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wt.DWORD),
            ("biWidth", wt.LONG),
            ("biHeight", wt.LONG),
            ("biPlanes", wt.WORD),
            ("biBitCount", wt.WORD),
            ("biCompression", wt.DWORD),
            ("biSizeImage", wt.DWORD),
            ("biXPelsPerMeter", wt.LONG),
            ("biYPelsPerMeter", wt.LONG),
            ("biClrUsed", wt.DWORD),
            ("biClrImportant", wt.DWORD),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]

    hdc_screen = user32.GetDC(0)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
    old = gdi32.SelectObject(hdc_mem, hbmp)
    try:
        ok = user32.PrintWindow(wt.HWND(hwnd), hdc_mem, PW_RENDERFULLCONTENT)
        if not ok:
            return Image.new("RGB", (1, 1))
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h  # 负数 = 自上而下
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0  # BI_RGB
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0)
        return Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)
    finally:
        gdi32.SelectObject(hdc_mem, old)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)


def grab(win: WindowInfo | None, method: str = "screen") -> CaptureResult:
    """抓取指定窗口；win=None 表示整个屏幕。

    method: "screen" 抓屏幕可见像素（所见即所得）；"window" 用 PrintWindow（可抓被遮挡窗口）。
    """
    make_dpi_aware()
    if win is None:
        bbox = (0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
        return CaptureResult(_grab_screen(bbox), "整个屏幕", time.time())

    if win.minimized:
        raise RuntimeError("目标窗口已最小化，请先还原窗口")

    if method == "window":
        img = _grab_printwindow(win.hwnd, win.w, win.h)
        if img.size[0] > 2 and img.getbbox() is not None:
            return CaptureResult(img, win.title, time.time())

    img = _grab_screen(win.rect)
    return CaptureResult(img, win.title, time.time())


def virtual_screen_rect() -> tuple[int, int, int, int]:
    """整个虚拟桌面（含多显示器）的物理像素范围。"""
    make_dpi_aware()
    # 76/77/78/79 = SM_XVIRTUALSCREEN/SM_YVIRTUALSCREEN/SM_CXVIRTUALSCREEN/SM_CYVIRTUALSCREEN
    return (
        user32.GetSystemMetrics(76),
        user32.GetSystemMetrics(77),
        user32.GetSystemMetrics(78),
        user32.GetSystemMetrics(79),
    )


def grab_region(rect: tuple[int, int, int, int]) -> CaptureResult:
    """抓取固定屏幕区域 (x, y, w, h)。"""
    make_dpi_aware()
    x, y, w, h = rect
    img = _grab_screen((int(x), int(y), int(x + w), int(y + h)))
    return CaptureResult(img, f"固定区域 {int(w)}×{int(h)}", time.time())


def overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    """两个 (x, y, w, h) 矩形是否相交。"""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def set_app_user_model_id(app_id: str) -> None:
    """让任务栏把我们当成独立程序（否则任务栏会显示 pythonw.exe 的图标）。"""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(ctypes.c_wchar_p(app_id))
    except Exception:
        pass


def set_window_icon(hwnd: int, ico_path: str) -> None:
    """显式设置窗口大/小图标，保证标题栏和任务栏一致。"""
    try:
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x10
        WM_SETICON = 0x0080
        for (w, h), which in (((32, 32), 1), ((16, 16), 0)):
            hicon = user32.LoadImageW(None, ico_path, IMAGE_ICON, w, h, LR_LOADFROMFILE)
            if hicon:
                user32.SendMessageW(wt.HWND(hwnd), WM_SETICON, which, hicon)
    except Exception:
        pass


def foreground_window() -> int:
    return int(user32.GetForegroundWindow() or 0)


def process_name(hwnd: int) -> str:
    """取窗口所属进程名（小写，如 chrome.exe）。"""
    try:
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(wt.HWND(hwnd), ctypes.byref(pid))
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wt.DWORD(len(buf))
            ok = kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
            return (buf.value.rsplit("\\", 1)[-1].lower()) if ok else ""
        finally:
            kernel32.CloseHandle(h)
    except Exception:
        return ""


def bring_to_front(hwnd: int) -> None:
    """把目标窗口提到最前（截图前置前，避免抓到被遮挡的画面）。"""
    try:
        if user32.IsIconic(wt.HWND(hwnd)):
            user32.ShowWindow(wt.HWND(hwnd), 9)  # SW_RESTORE
        user32.SetForegroundWindow(wt.HWND(hwnd))
    except Exception:
        pass


def diff_score(a: Image.Image, b: Image.Image, size: int = 64) -> float:
    """两帧画面差异评分（0~255）。先把图缩小到 64x64 灰度再比较，速度快且抗噪。"""
    try:
        ga = a.convert("L").resize((size, size), Image.BILINEAR)
        gb = b.convert("L").resize((size, size), Image.BILINEAR)
        d = ImageChops.difference(ga, gb)
        return float(ImageStat.Stat(d).mean[0])
    except Exception:
        return 999.0


def to_data_url(img: Image.Image, max_side: int = 1600, quality: int = 88) -> str:
    """把图片编码成 data:image/jpeg;base64,...，供视觉模型使用。"""
    import base64
    import io

    im = img
    if max(im.size) > max_side:
        scale = max_side / max(im.size)
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)
    if im.mode != "RGB":
        im = im.convert("RGB")
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


