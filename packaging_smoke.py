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
    from classroom.openwhispr_import import transcript_rows
    assert transcript_rows('[{"text":"Synthetic import check","timestamp":2}]')[0][0][2]==2
    import tempfile
    # Locator imports load configuration. Keep the check outside the real profile.
    original_data_dir = os.environ.get('CLICKY_DATA_DIR')
    with tempfile.TemporaryDirectory(prefix='clicky-cursor-check-') as cursor_data:
        os.environ['CLICKY_DATA_DIR'] = cursor_data
        try:
            # Exercise frozen imports and real Drive code with fake input only.
            import asyncio
            from contextlib import contextmanager
            from types import SimpleNamespace
            from ai import pointing
            from ai.element_locator import Detected
            from drive import validate_plan, DriveController
            import tutor
            @contextmanager
            def replace(obj, name, value):
                original = getattr(obj, name)
                setattr(obj, name, value)
                try:
                    yield
                finally:
                    setattr(obj, name, original)
            shot = SimpleNamespace(index=1, width=100, height=100, base64_jpeg='',
                physical_left=0, physical_top=0, physical_width=100, physical_height=100,
                logical_left=0, logical_top=0, dpi_scale=1)
            async def cursor_check():
                async def miss(**kw): return None
                async def hit(**kw): return Detected(50,50,1)
                with replace(pointing.hybrid_pointer, 'find_target', lambda *a,**kw: None), \
                     replace(pointing.element_locator, 'is_available', lambda *a: True), \
                     replace(pointing.element_locator, 'detect_element', miss), \
                     replace(pointing.universal_locator, 'detect_element_universal', hit):
                    assert (await pointing.locate_target(shot=shot,query='synthetic target',llm=object())).x == 50
                class FakeMouse:
                    position = (0,0)
                    def press(self, *args): raise AssertionError('Unexpected click')
                    def release(self, *args): raise AssertionError('Unexpected release')
                mouse = FakeMouse()
                plan = validate_plan({'title':'Synthetic hover','actions':[{'kind':'move','x':500,'y':500}]})
                with replace(tutor, 'active_window_title', lambda:'Synthetic test'):
                    await DriveController().run(plan,shot,mouse=mouse,keyboard=object())
                assert mouse.position == (50,50)
            asyncio.run(cursor_check())
        finally:
            if original_data_dir is None:
                os.environ.pop('CLICKY_DATA_DIR', None)
            else:
                os.environ['CLICKY_DATA_DIR'] = original_data_dir

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
                         "six dashboard pages", "Classroom without capture", "bundled SVG icons", "sherpa-onnx import", "OpenWhispr importer",
                         "same-request pointer fallback", "move-only Drive with fake input"],
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
