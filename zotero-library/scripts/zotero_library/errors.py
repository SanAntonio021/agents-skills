class LibraryError(Exception):
    """Only fixed public codes cross the CLI boundary."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


class NativeRejected(LibraryError):
    """Authoritative fixed-program rejection before a native job was created."""
