"""Exercise the shipped Qt runtime without starting Clicky's background services."""
import json
import sys


def run():
    import os
    if os.name == 'nt':
        import ctypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.GetCurrentProcess.restype=ctypes.c_void_p
        kernel.SetPriorityClass.argtypes=[ctypes.c_void_p,ctypes.c_uint]
        assert kernel.SetPriorityClass(kernel.GetCurrentProcess(),0x4000)
    from PyQt6.QtCore import QT_VERSION_STR, qVersion
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget
    from drawing import example_scene
    from ui.drawing_board import SketchCanvas
    from audio.devices import open_input_stream
    from audio.tts.edge_tts_provider import EdgeTTSProvider
    from importlib.metadata import version
    from ui.dashboard import DashboardWindow
    from ui.dashboard_icons import icon
    import sherpa_onnx

    edge_version = version('edge-tts')
    assert tuple(map(int, edge_version.split('.')[:2])) >= (7, 3), 'Edge speech needs the updated handshake'

    app = QApplication.instance() or QApplication([])
    window = QWidget()
    layout = QVBoxLayout(window)
    layout.addWidget(QLabel("Clicky packaged startup check"))
    layout.addWidget(SketchCanvas(example_scene()))
    window.resize(800, 600)
    window.show()
    app.processEvents()
    image = QImage(window.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    window.render(painter)
    painter.end()
    assert not image.isNull()
    window.close()
    dashboard = DashboardWindow(preview=True)
    dashboard.show()
    for page in dashboard.PAGES:
        dashboard.select_page(page)
        app.processEvents()
        assert not dashboard.grab().isNull()
    assert dashboard.classroom.recorder is None
    assert not icon('notebook-pen').isNull(), 'Bundled dashboard icons are missing'
    dashboard.close()
    app.processEvents()
    report = {"ok": True, "qt_binding": QT_VERSION_STR, "qt_runtime": qVersion(),
              "checks": ["QtWidgets import", "native window", "Sketch rendering", "audio capture import", "Edge voice import",
                         "six dashboard pages", "Classroom without capture", "bundled SVG icons", "sherpa-onnx import"],
              "edge_tts": edge_version,
              "services_started": False}
    if '--smoke-audio' in sys.argv:
        # Explicit prerecorded fixture only; no microphone, playback or device API.
        from classroom.settings import Settings
        from classroom.recorder import import_audio, retry_session
        audio=sys.argv[sys.argv.index('--smoke-audio')+1]
        model=sys.argv[sys.argv.index('--smoke-model')+1]
        session=import_audio(audio,'Packaged speech fixture',Settings(engine='parakeet',
            parakeet_directory=model,automatic_notes=False,threads=1))
        retry_session(session)
        rows=session.rows()
        text=' '.join(r['text'] for r in rows if r['status']=='done')
        assert text and not session.has_errors(), 'Packaged transcription did not finish'
        report['speech']={'chunks':len(rows),'allChunksProcessed':True,'words':len(text.split()),
                          'threads':1,'liveDevicesUsed':False,'session':str(session.path)}
    if "--smoke-report" in sys.argv:
        from pathlib import Path
        Path(sys.argv[sys.argv.index("--smoke-report") + 1]).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    return 0
