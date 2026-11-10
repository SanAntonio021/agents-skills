"""Hidden Word connection through its documented document-window native model.

This explicit fallback avoids Word.Application activation when another suite
owns that COM entry. The shared gate still verifies the registered executable,
COM path, new process image and real Word.Window.Hwnd before document work.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

import office_native_gate as gate
from reference_word import _NativeWordApplication, _registered_word_server


def _user_api():
    api = ctypes.WinDLL('user32', use_last_error=True)
    api.GetThreadDesktop.argtypes = [wintypes.DWORD]
    api.GetThreadDesktop.restype = wintypes.HANDLE
    api.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int,
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    api.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenInputDesktop.restype = wintypes.HANDLE
    api.CloseDesktop.argtypes = [wintypes.HANDLE]
    return api


def _object_name(api, handle):
    needed = wintypes.DWORD()
    api.GetUserObjectInformationW(handle, 2, None, 0, ctypes.byref(needed))
    buffer = ctypes.create_unicode_buffer(max(needed.value // 2, 1))
    if not api.GetUserObjectInformationW(handle, 2, buffer, ctypes.sizeof(buffer), ctypes.byref(needed)):
        raise ctypes.WinError(ctypes.get_last_error())
    return buffer.value


def desktop_evidence():
    api = _user_api()
    kernel = ctypes.WinDLL('kernel32')
    kernel.GetCurrentThreadId.restype = wintypes.DWORD
    current = _object_name(api, api.GetThreadDesktop(kernel.GetCurrentThreadId()))
    handle = api.OpenInputDesktop(0, False, 1)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        visible = _object_name(api, handle)
    finally:
        api.CloseDesktop(handle)
    return {'worker_desktop': current, 'input_desktop': visible,
            'isolated': current.startswith('CodexWord_') and current != visible}


def run_on_private_desktop(script, arguments=(), *, timeout=600):
    """Run one Python worker without ever switching the user's input desktop."""
    api = _user_api()
    api.CreateDesktopW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    api.CreateDesktopW.restype = wintypes.HANDLE
    name = 'CodexWord_' + uuid.uuid4().hex
    desktop = api.CreateDesktopW(name, None, None, 0, 0xF01FF, None)
    if not desktop:
        raise ctypes.WinError(ctypes.get_last_error())
    import msvcrt
    import os
    import win32con
    import win32event
    import win32process
    startup = win32process.STARTUPINFO()
    startup.lpDesktop = 'WinSta0\\' + name
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    command = [sys.executable, '-B', '-X', 'utf8', str(Path(script).resolve()), *arguments]
    try:
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors, open(os.devnull, 'rb') as stdin:
            handles = [msvcrt.get_osfhandle(f.fileno()) for f in (stdin, output, errors)]
            for handle in handles:
                os.set_handle_inheritable(handle, True)
            startup.dwFlags |= win32con.STARTF_USESTDHANDLES
            startup.hStdInput, startup.hStdOutput, startup.hStdError = handles
            try:
                process, thread, pid, _ = win32process.CreateProcess(sys.executable,
                    subprocess.list2cmdline(command), None, None, True,
                    subprocess.CREATE_NO_WINDOW, None, None, startup)
            finally:
                for handle in handles:
                    os.set_handle_inheritable(handle, False)
            thread.Close()
            try:
                if win32event.WaitForSingleObject(process, int(timeout * 1000)) == win32con.WAIT_TIMEOUT:
                    win32process.TerminateProcess(process, 1)
                    raise subprocess.TimeoutExpired(command, timeout)
                code = win32process.GetExitCodeProcess(process)
            finally:
                process.Close()
            output.seek(0)
            errors.seek(0)
            return subprocess.CompletedProcess(command, code,
                output.read().decode('utf-8', errors='replace'), errors.read().decode('utf-8', errors='replace'))
    finally:
        api.CloseDesktop(desktop)


class _WordProcess:
    def __init__(self, executable, arguments, desktop):
        import win32process
        startup = win32process.STARTUPINFO()
        startup.lpDesktop = 'WinSta0\\' + desktop
        startup.dwFlags |= 1
        startup.wShowWindow = 0
        self.handle, thread, self.pid, _ = win32process.CreateProcess(str(executable),
            subprocess.list2cmdline([str(executable), *arguments]), None, None, False,
            subprocess.CREATE_NO_WINDOW, None, None, startup)
        thread.Close()

    def poll(self):
        import win32process
        code = win32process.GetExitCodeProcess(self.handle)
        return None if code == 259 else code

    @property
    def returncode(self):
        return self.poll()

    def wait(self, timeout):
        import win32event
        if win32event.WaitForSingleObject(self.handle, int(timeout * 1000)) == 258:
            raise subprocess.TimeoutExpired('owned Word', timeout)
        return self.poll()

    def terminate(self):
        import win32process
        win32process.TerminateProcess(self.handle, 1)

    def __del__(self):
        if getattr(self, 'handle', None):
            self.handle.Close()


def _pids():
    import psutil
    return sorted(p.pid for p in psutil.process_iter(['name'])
                  if (p.info['name'] or '').lower() == 'winword.exe')


def _windows(pid):
    import win32gui
    import win32process
    result, tops = [], []
    def add(hwnd, _):
        if win32process.GetWindowThreadProcessId(hwnd)[1] == pid:
            result.append({'hwnd': int(hwnd), 'class': win32gui.GetClassName(hwnd),
                           'visible': bool(win32gui.IsWindowVisible(hwnd))})
    def top(hwnd, _):
        if win32process.GetWindowThreadProcessId(hwnd)[1] == pid:
            tops.append(hwnd)
            add(hwnd, None)
    win32gui.EnumWindows(top, None)
    for hwnd in tops:
        win32gui.EnumChildWindows(hwnd, add, None)
    return result


class _WindowApplication(_NativeWordApplication):
    def __init__(self, application, registered_path, window):
        super().__init__(application, registered_path)
        object.__setattr__(self, '_native_window', window)

    @property
    def Hwnd(self):
        # Microsoft Word exposes this property on Window, not Application.
        if self._native_window is None:
            raise RuntimeError('Bootstrap window was closed after ownership verification')
        return int(self._native_window.Hwnd)


class NativeWordConnector:
    """Pass this factory and its prepare method together to the shared gate."""
    def __init__(self):
        self.evidence = []
        self._pending = {}

    def __call__(self, progid):
        import psutil
        import pythoncom
        import win32process
        from win32com.client import dynamic
        from comtypes import GUID, POINTER
        from comtypes.automation import IDispatch
        from docx import Document

        desktop = desktop_evidence()
        if not desktop['isolated']:
            raise RuntimeError('Native Word fallback requires its private, non-input desktop worker')
        if progid != 'Word.Application' or _pids():
            raise RuntimeError('A new exclusive Word instance is required')
        word = _registered_word_server(progid).resolve()
        root = Path(tempfile.gettempdir()) / 'codex-docx-gates'
        if root.is_symlink():
            raise RuntimeError('Refusing linked temporary root')
        root.mkdir(exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix='word-nativeom_', dir=root))
        blank = work / 'bootstrap.docx'
        document = Document()
        document.add_paragraph('Isolated Word connection bootstrap.')
        document.save(blank)
        rec = {'method': 'AccessibleObjectFromWindow/_WwG', 'status': 'starting',
               'word_executable': str(word), 'bootstrap': str(blank), 'attempts': [],
               'desktop': desktop}
        self.evidence.append(rec)
        proc = _WordProcess(word, ['/a', '/n', '/q', str(blank)], desktop['worker_desktop'])
        rec['pid'] = proc.pid
        app = None
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                pids = _pids()
                if pids and pids != [proc.pid]:
                    raise RuntimeError('Unexpected Word process appeared')
                if proc.poll() is not None:
                    raise RuntimeError(f'Word exited with {proc.returncode}')
                if Path(psutil.Process(proc.pid).exe()).resolve() != word:
                    raise RuntimeError('New process executable differs from registered Word')
                windows = _windows(proc.pid)
                if any(w['visible'] for w in windows if w['class'] == 'OpusApp'):
                    raise RuntimeError('Word became visible; background-only connection refused')
                oleacc = ctypes.WinDLL('oleacc')
                oleacc.AccessibleObjectFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD,
                    ctypes.POINTER(GUID), ctypes.POINTER(POINTER(IDispatch))]
                oleacc.AccessibleObjectFromWindow.restype = ctypes.c_long
                iid = GUID('{00020400-0000-0000-C000-000000000046}')
                for pane in (w for w in windows if w['class'] == '_WwG'):
                    ptr = POINTER(IDispatch)()
                    hr = oleacc.AccessibleObjectFromWindow(pane['hwnd'], 0xFFFFFFF0,
                                                          ctypes.byref(iid), ctypes.byref(ptr))
                    rec['attempts'].append({'pane': pane, 'hresult': hr})
                    if hr == 0 and ptr:
                        address = ctypes.cast(ptr, ctypes.c_void_p).value
                        window = dynamic.Dispatch(pythoncom.ObjectFromAddress(address, pythoncom.IID_IDispatch))
                        app = window.Application
                        break
                if app is not None:
                    break
                time.sleep(.2)
            if app is None:
                raise RuntimeError('Word document-window native object was unavailable')
            wrapped = _WindowApplication(app, word, window)
            identity = gate._application_identity(wrapped)
            rec['identity'] = identity
            rec['native_window_hwnd'] = int(window.Hwnd)
            if win32process.GetWindowThreadProcessId(rec['native_window_hwnd'])[1] != proc.pid:
                raise RuntimeError('Native window belongs to another process')
            observation = {'status': 'OBSERVED', 'owned_pids': [proc.pid], 'pre_dispatch_pids': []}
            rec['ownership'] = gate._verify_word_ownership(wrapped, identity, observation)
            if int(app.Documents.Count) != 1 or Path(str(app.Documents.Item(1).FullName)).resolve() != blank:
                raise RuntimeError('Unexpected document in new Word instance')
            self._pending[id(wrapped)] = (blank, work, rec)
            rec['status'] = 'connected_bootstrap_open'
            return wrapped
        except BaseException as exc:
            rec.update(status='failed', error=f'{type(exc).__name__}: {exc}')
            if app is not None and rec.get('ownership'):
                try:
                    app.Quit(SaveChanges=0)
                    proc.wait(timeout=10)
                    rec['failure_cleanup'] = 'normal_exit'
                except Exception as cleanup_exc:
                    rec['cleanup_error'] = str(cleanup_exc)
            # Before this factory returns, only its generated blank file can
            # have been opened. Never terminate a pre-existing Word process.
            if proc.poll() is None and Path(psutil.Process(proc.pid).exe()).resolve() == word:
                proc.terminate()
                proc.wait(timeout=10)
                rec['failure_cleanup'] = 'terminated_owned_bootstrap_process'
            if proc.poll() is not None:
                blank.unlink(missing_ok=True)
                if not any(work.iterdir()):
                    work.rmdir()
            raise

    def prepare(self, application):
        """Close the generated bootstrap after the shared ownership checks."""
        blank, work, rec = self._pending[id(application)]
        if int(application.Documents.Count) != 1:
            raise RuntimeError('Unexpected document count before bootstrap close')
        document = application.Documents.Item(1)
        if Path(str(document.FullName)).resolve() != blank:
            raise RuntimeError('Unexpected bootstrap document path')
        for name, value in (('Visible', False), ('DisplayAlerts', 0),
                            ('ScreenUpdating', False), ('AutomationSecurity', 3)):
            gate._set_and_verify(application, name, value)
        document.Close(SaveChanges=0)
        # Do not retain a stale Window COM reference while waiting for Quit.
        object.__setattr__(application, '_native_window', None)
        if int(application.Documents.Count) != 0:
            raise RuntimeError('Bootstrap document did not close')
        blank.unlink()
        work.rmdir()
        self._pending.pop(id(application))
        rec.update(status='connected', bootstrap_closed=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    parser.add_argument('--allow-office-com', action='store_true')
    parser.add_argument('--require-render', action='store_true')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--private-worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.report and args.report.resolve() == args.file.resolve():
        parser.error('report must differ from the document')
    if not args.private_worker:
        arguments = list(sys.argv[1:] if argv is None else argv) + ['--private-worker']
        completed = run_on_private_desktop(__file__, arguments)
        print(completed.stdout, end='')
        if completed.stderr:
            print(completed.stderr, file=sys.stderr, end='')
        return completed.returncode
    connector = NativeWordConnector()
    result = gate.check_file(args.file, 'docx', allow_office_com=args.allow_office_com,
        require_render=args.require_render, dispatch_ex=connector,
        prepare_owned_application=connector.prepare, process_exit_timeout_seconds=30)
    result['connection'] = connector.evidence
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report:
        args.report.write_text(payload, encoding='utf-8')
    print(payload)
    return 0 if result.get('ok') else 1


if __name__ == '__main__':
    raise SystemExit(main())
