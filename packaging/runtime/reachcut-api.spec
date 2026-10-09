from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules


repository_root = Path(SPEC).resolve().parents[2]
datas = []
binaries = []
hiddenimports = collect_submodules("clipper")

# These libraries discover native binaries, model metadata, or plug-ins dynamically.
for package in ("av", "ctranslate2", "cv2", "faster_whisper", "onnxruntime", "yt_dlp"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

analysis = Analysis(
    [str(repository_root / "packaging" / "runtime" / "api_entry.py")],
    pathex=[str(repository_root / "apps" / "api" / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "ruff", "mypy"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="reachcut-api",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # The agent hides child windows on Windows. Keeping console streams available here is
    # required because URL imports recursively invoke this executable and capture yt-dlp
    # stdout/stderr.
    console=True,
)

collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="reachcut-api",
)
