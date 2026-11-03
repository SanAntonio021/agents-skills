"""Local API authorization. Secrets live in memory or Windows Credential Manager only."""
import ctypes
import os
from ctypes import wintypes

from .errors import LibraryError


class Credential(ctypes.Structure):
    _fields_ = [('Flags', wintypes.DWORD), ('Type', wintypes.DWORD),
                ('TargetName', wintypes.LPWSTR), ('Comment', wintypes.LPWSTR),
                ('LastWritten', wintypes.FILETIME), ('CredentialBlobSize', wintypes.DWORD),
                ('CredentialBlob', ctypes.POINTER(ctypes.c_ubyte)), ('Persist', wintypes.DWORD),
                ('AttributeCount', wintypes.DWORD), ('Attributes', ctypes.c_void_p),
                ('TargetAlias', wintypes.LPWSTR), ('UserName', wintypes.LPWSTR)]


class Vault:
    def __init__(self, binding):
        self.target = 'ZoteroLibrary/LocalAPI/' + binding

    def _api(self):
        if os.name != 'nt':
            raise LibraryError('windows_credential_manager_unavailable')
        api = ctypes.WinDLL('Advapi32.dll', use_last_error=True)
        api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                 ctypes.POINTER(ctypes.POINTER(Credential))]
        api.CredReadW.restype = wintypes.BOOL
        api.CredWriteW.argtypes = [ctypes.POINTER(Credential), wintypes.DWORD]
        api.CredWriteW.restype = wintypes.BOOL
        api.CredFree.argtypes = [ctypes.c_void_p]
        return api

    def get(self):
        api = self._api()
        pointer = ctypes.POINTER(Credential)()
        if not api.CredReadW(self.target, 1, 0, ctypes.byref(pointer)):
            if ctypes.get_last_error() == 1168:
                return None
            raise LibraryError('credential_store_unavailable')
        try:
            return ctypes.string_at(pointer.contents.CredentialBlob,
                                    pointer.contents.CredentialBlobSize).decode('utf-8')
        finally:
            api.CredFree(pointer)

    def put(self, secret):
        api = self._api()
        blob = (ctypes.c_ubyte * len(secret.encode()))(*secret.encode())
        credential = Credential(Type=1, TargetName=self.target, UserName='Zotero Local API',
                                CredentialBlobSize=len(blob), CredentialBlob=blob, Persist=2)
        if not api.CredWriteW(ctypes.byref(credential), 0):
            raise LibraryError('credential_store_unavailable')

    def forget(self):
        api = self._api()
        api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        if not api.CredDeleteW(self.target, 1, 0) and ctypes.get_last_error() != 1168:
            raise LibraryError('credential_store_unavailable')
