"""Store SMTP credentials without putting a password in process arguments or files."""
import ctypes as C


def store_password(service, account, password):
    if not account or not password:
        raise ValueError('Enter the SMTP username and app password')
    sec = C.CDLL('/System/Library/Frameworks/Security.framework/Security')
    cf = C.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
    sec.SecKeychainAddGenericPassword.argtypes = [C.c_void_p, C.c_uint32, C.c_char_p, C.c_uint32, C.c_char_p, C.c_uint32, C.c_char_p, C.POINTER(C.c_void_p)]
    sec.SecKeychainAddGenericPassword.restype = C.c_int32
    sec.SecKeychainFindGenericPassword.argtypes = [C.c_void_p, C.c_uint32, C.c_char_p, C.c_uint32, C.c_char_p, C.c_void_p, C.c_void_p, C.POINTER(C.c_void_p)]
    sec.SecKeychainFindGenericPassword.restype = C.c_int32
    sec.SecKeychainItemModifyAttributesAndData.argtypes = [C.c_void_p, C.c_void_p, C.c_uint32, C.c_char_p]
    sec.SecKeychainItemModifyAttributesAndData.restype = C.c_int32
    cf.CFRelease.argtypes = [C.c_void_p]
    service, account, password = [s.encode('utf-8') for s in (service, account, password)]
    status = sec.SecKeychainAddGenericPassword(None, len(service), service, len(account), account, len(password), password, None)
    if status == -25299:  # errSecDuplicateItem
        item = C.c_void_p()
        status = sec.SecKeychainFindGenericPassword(None, len(service), service, len(account), account, None, None, C.byref(item))
        if status == 0:
            try:
                status = sec.SecKeychainItemModifyAttributesAndData(item, None, len(password), password)
            finally:
                cf.CFRelease(item)
    if status:
        raise ValueError(f'Keychain could not save the password (macOS status {status})')
