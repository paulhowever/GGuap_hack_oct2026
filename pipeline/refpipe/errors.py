class RefpipeError(Exception):
    pass


class UsdxError(RefpipeError):
    pass


class MetaError(RefpipeError):
    pass


class CutError(RefpipeError):
    pass


class MidiError(RefpipeError):
    pass
