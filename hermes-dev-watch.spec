# PyInstaller spec: one-file app, no console window. Build: pyinstaller hermes-dev-watch.spec  ->  dist/hermes-dev-watch(.exe)
# The app uses WebView2 (Windows) or GTK/WebKit (Linux); Qt and Tk backends are excluded so they are not bundled.
EXCLUDE = ["PyQt5", "PyQt6", "PySide2", "PySide6", "qtpy", "tkinter", "matplotlib", "numpy", "PIL"]
a = Analysis(["run.py"], datas=[("hermes_dev_watch/static", "hermes_dev_watch/static")], excludes=EXCLUDE)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="hermes-dev-watch", console=False, upx=False)
