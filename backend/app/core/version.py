from importlib.metadata import PackageNotFoundError, version


def app_version() -> str:
    try:
        return version("karaoke-backend")
    except PackageNotFoundError:
        return "0.0.0+local"
