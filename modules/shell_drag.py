"""把文件从窗口里拖到桌面/资源管理器：Windows OLE 最小拖放源。

不引入 PyQt/pywin32；只用 ctypes 调 shell32/ole32。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import uuid

HRESULT = ctypes.c_long
ULONG = ctypes.c_ulong
DWORD = wt.DWORD
UINT = wt.UINT

S_OK = 0
E_NOINTERFACE = 0x80004002
DRAGDROP_S_DROP = 0x00040100
DRAGDROP_S_CANCEL = 0x00040101
DRAGDROP_S_USEDEFAULTCURSORS = 0x00040102
DROPEFFECT_COPY = 1
DROPEFFECT_MOVE = 2
MK_LBUTTON = 0x0001


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid(text: str) -> GUID:
    return GUID.from_buffer_copy(uuid.UUID(text).bytes_le)


IID_IUNKNOWN = _guid("00000000-0000-0000-C000-000000000046")
IID_IDROPSOURCE = _guid("00000121-0000-0000-C000-000000000046")
IID_IDATAOBJECT = _guid("0000010e-0000-0000-C000-000000000046")


def _same(g: GUID, ref: GUID) -> bool:
    return bytes(g) == bytes(ref)


_QI = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p,
                         ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
_ADDR = ctypes.WINFUNCTYPE(ULONG, ctypes.c_void_p)
_REL = ctypes.WINFUNCTYPE(ULONG, ctypes.c_void_p)
_QCD = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wt.BOOL, DWORD)
_GF = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, DWORD)


class IDropSourceVtbl(ctypes.Structure):
    _fields_ = [
        ("QueryInterface", _QI),
        ("AddRef", _ADDR),
        ("Release", _REL),
        ("QueryContinueDrag", _QCD),
        ("GiveFeedback", _GF),
    ]


class DropSource(ctypes.Structure):
    _fields_ = [("lpVtbl", ctypes.POINTER(IDropSourceVtbl))]


def _release_data_object(pdo: ctypes.c_void_p) -> None:
    try:
        vtbl = ctypes.cast(pdo, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        fn = ctypes.WINFUNCTYPE(ULONG, ctypes.c_void_p)(vtbl[2])
        fn(pdo)
    except Exception:
        pass


def _create_data_object(path: str):
    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32
    pidl = ctypes.c_void_p()
    attrs = UINT(0)
    hr = shell32.SHParseDisplayName(
        ctypes.c_wchar_p(path), None, ctypes.byref(pidl), 0, ctypes.byref(attrs))
    if hr != 0 or not pidl:
        return None, None
    apidl = (ctypes.c_void_p * 1)()
    apidl[0] = pidl
    pdo = ctypes.c_void_p()
    hr = shell32.SHCreateDataObject(
        None, 1, apidl, None, ctypes.byref(IID_IDATAOBJECT), ctypes.byref(pdo))
    if hr != 0 or not pdo:
        try:
            ole32.CoTaskMemFree(pidl)
        except Exception:
            pass
        return None, None
    return pdo, pidl


def drag_file(path: str) -> dict:
    """在当前 Tk 线程调用；返回 {'ok','effect','exists'}。

    默认允许复制/移动，具体由 Windows 资源管理器根据 Ctrl 和磁盘决定。
    """
    path = os.path.abspath(path)
    result = {"ok": False, "effect": 0, "exists": os.path.exists(path),
              "path": path}
    if not os.path.exists(path):
        return result
    ole32 = ctypes.windll.ole32
    try:
        ole32.OleInitialize(None)
    except Exception:
        pass
    pdo = None
    pidl = None
    try:
        pdo, pidl = _create_data_object(path)
        if not pdo:
            return result
        state = {"ref": 1}

        @_QI
        def query_interface(this, riid, ppv):
            try:
                g = riid.contents
                if _same(g, IID_IDROPSOURCE) or _same(g, IID_IUNKNOWN):
                    ppv[0] = this
                    state["ref"] += 1
                    return S_OK
            except Exception:
                pass
            try:
                ppv[0] = None
            except Exception:
                pass
            return E_NOINTERFACE

        @_ADDR
        def add_ref(_this):
            state["ref"] += 1
            return state["ref"]

        @_REL
        def release(_this):
            state["ref"] -= 1
            return max(0, state["ref"])

        @_QCD
        def query_continue(_this, escape, keys):
            if escape:
                return DRAGDROP_S_CANCEL
            if not (int(keys) & MK_LBUTTON):
                return DRAGDROP_S_DROP
            return S_OK

        @_GF
        def give_feedback(_this, _effect):
            return DRAGDROP_S_USEDEFAULTCURSORS

        vtbl = IDropSourceVtbl(query_interface, add_ref, release,
                               query_continue, give_feedback)
        src = DropSource(ctypes.pointer(vtbl))
        effect = DWORD(0)
        ole32.DoDragDrop.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                     DWORD, ctypes.POINTER(DWORD)]
        ole32.DoDragDrop.restype = HRESULT
        hr = ole32.DoDragDrop(ctypes.c_void_p(pdo), ctypes.byref(src),
                              DROPEFFECT_COPY | DROPEFFECT_MOVE,
                              ctypes.byref(effect))
        result["effect"] = int(effect.value)
        result["exists"] = os.path.exists(path)
        result["ok"] = int(hr) == 0
        result["hr"] = int(hr)
        return result
    except Exception as e:
        result["error"] = str(e)
        return result
    finally:
        if pdo:
            _release_data_object(pdo)
        if pidl:
            try:
                ole32.CoTaskMemFree(pidl)
            except Exception:
                pass
        try:
            ole32.OleUninitialize()
        except Exception:
            pass
