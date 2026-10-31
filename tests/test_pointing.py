"""Cursor regression tests use synthetic images and fake input, never the desktop."""
import asyncio
import base64
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from PIL import Image

from ai import element_locator as locator, pointing
from ai.universal_locator import _parse_cell_number
from drive import DriveController, validate_plan, is_action_request
from tutor import is_locate


@pytest.fixture
def shot():
    image = io.BytesIO()
    Image.new('RGB', (1280, 800), '#334455').save(image, format='JPEG')
    return SimpleNamespace(base64_jpeg=base64.b64encode(image.getvalue()).decode(),
        width=1280, height=800, index=1, physical_width=2560, physical_height=1600,
        physical_left=-2560, physical_top=0, logical_left=-1707, logical_top=20, dpi_scale=1.5)


@pytest.fixture(autouse=True)
def reset_backoff(monkeypatch):
    monkeypatch.setattr(locator, '_unavailable_until', {})
    monkeypatch.setattr(locator.cfg, 'anthropic_api_key', 'synthetic-test-key')


def options(shot):
    return dict(screenshot_jpeg_b64=shot.base64_jpeg, original_width=shot.width,
        original_height=shot.height, screen_index=shot.index, user_question='Show me the bottom of this CAD part',
        physical_width=shot.physical_width, physical_height=shot.physical_height,
        physical_left=shot.physical_left, physical_top=shot.physical_top,
        logical_left=shot.logical_left, logical_top=shot.logical_top, dpi_scale=shot.dpi_scale)


def mock_api(monkeypatch, response, status=200):
    requests = []
    class Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kw):
            requests.append(kw)
            return httpx.Response(status, json=response)
    monkeypatch.setattr(locator.httpx, 'AsyncClient', Client)
    return requests


@pytest.mark.parametrize('model,tool,beta', [
    (None, 'computer_toolset_20260801', None),
    ('claude-sonnet-4-6', 'computer_20251124', 'computer-use-2025-11-24'),
    ('claude-haiku-4-5-20251001', 'computer_20250124', 'computer-use-2025-01-24'),
])
def test_claude_protocol_and_dpi(monkeypatch, shot, model, tool, beta):
    block = {'type':'tool_use', 'name':'computer' if beta else 'mouse_move',
             'toolset_name':'computer', 'input':{'coordinate':[640,400], 'action':'mouse_move'}}
    requests = mock_api(monkeypatch, {'content':[block]})
    result = asyncio.run(locator.detect_element(**options(shot), model=model))
    assert (result.x, result.y) == (-854, 553)
    assert requests[0]['json']['tools'][0]['type'] == tool
    assert requests[0]['headers'].get('anthropic-beta') == beta
    assert 'CAD part' in requests[0]['json']['messages'][0]['content'][1]['text']
    if not beta:
        configs = requests[0]['json']['tools'][0]['configs']
        assert [name for name, config in configs.items() if config['enabled']] == ['mouse_move']
        assert 'display_width_px' not in requests[0]['json']['tools'][0]


@pytest.mark.parametrize('coord', [[float('nan'),2], [1,float('inf')], [-1,2], [1280,2],
                                  [True,2], ['10',2], [10], None])
def test_invalid_coordinates_are_never_clamped_into_a_target(monkeypatch, shot, coord):
    mock_api(monkeypatch, {'content':[{'type':'tool_use','name':'mouse_move',
        'toolset_name':'computer','input':{'coordinate':coord}}]})
    assert asyncio.run(locator.detect_element(**options(shot))) is None


def test_click_tool_is_not_a_location_suggestion(monkeypatch, shot):
    mock_api(monkeypatch, {'content':[{'type':'tool_use','name':'left_click',
        'toolset_name':'computer','input':{'coordinate':[640,400]}}]})
    assert asyncio.run(locator.detect_element(**options(shot))) is None


def test_refused_model_does_not_block_another_model(monkeypatch, shot):
    mock_api(monkeypatch, {}, 400)
    assert asyncio.run(locator.detect_element(**options(shot), model='claude-sonnet-4-6')) is None
    assert not locator.is_available('claude-sonnet-4-6')
    assert locator.is_available('claude-sonnet-5-5')


@pytest.mark.parametrize('failure', [None, RuntimeError('synthetic failure')])
def test_fallback_runs_in_the_same_request(monkeypatch, shot, failure):
    monkeypatch.setattr(pointing.hybrid_pointer, 'find_target', lambda *a, **kw: None)
    first = AsyncMock(side_effect=failure) if failure else AsyncMock(return_value=None)
    fallback = AsyncMock(return_value=locator.Detected(-800,500,1))
    monkeypatch.setattr(locator, 'detect_element', first)
    monkeypatch.setattr(pointing.universal_locator, 'detect_element_universal', fallback)
    result = asyncio.run(pointing.locate_target(shot=shot,query='bottom of part',llm=object()))
    assert result.x == -800 and first.await_count == fallback.await_count == 1
    assert fallback.call_args.kwargs['logical_left'] == -1707


def test_local_hit_skips_cloud_and_converts_physical_origin(monkeypatch, shot):
    monkeypatch.setattr(pointing.hybrid_pointer, 'find_target', lambda *a, **kw:
        SimpleNamespace(source='uia', x=-1280, y=800))
    cloud = AsyncMock()
    monkeypatch.setattr(locator, 'detect_element', cloud)
    result = asyncio.run(pointing.locate_target(shot=shot,query='Save',llm=object()))
    assert (result.x,result.y) == (-854,553)
    cloud.assert_not_awaited()


def test_cancellation_does_not_start_fallback(monkeypatch, shot):
    monkeypatch.setattr(pointing.hybrid_pointer, 'find_target', lambda *a, **kw: None)
    monkeypatch.setattr(locator, 'detect_element', AsyncMock(side_effect=asyncio.CancelledError))
    fallback = AsyncMock()
    monkeypatch.setattr(pointing.universal_locator, 'detect_element_universal', fallback)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(pointing.locate_target(shot=shot,query='part',llm=object()))
    fallback.assert_not_awaited()


@pytest.mark.parametrize('text', ['{"cell":0,"reason":"2 visible objects"}',
    '{"cell":true}', '{"cell":1.5}', '{"cell":"12"}', '0, not 12'])
def test_no_target_does_not_pick_unrelated_digits(text):
    assert _parse_cell_number(text,96) is None


@pytest.mark.parametrize('query', ['Move the mouse to Save', 'Hover over the bottom face',
                                  'Move cursor over that blue part'])
def test_mouse_requests_trigger_location(query):
    assert is_locate(query)
    assert is_action_request(query)


def test_move_only_uses_fake_mouse_without_clicks_or_keys(monkeypatch, shot):
    import tutor
    monkeypatch.setattr(tutor,'active_window_title',lambda:'Synthetic test')
    class FakeMouse:
        position=(0,0)
        def press(self,*args): pytest.fail('move must not press')
        def release(self,*args): pytest.fail('move must not release')
    fake = FakeMouse()
    plan = validate_plan({'title':'Hover','actions':[{'kind':'move','x':500,'y':500}]})
    asyncio.run(DriveController().run(plan,shot,mouse=fake,keyboard=object()))
    assert fake.position == (-1280,800)


def test_move_retains_sensitive_window_guard(monkeypatch, shot):
    import tutor
    monkeypatch.setattr(tutor,'active_window_title',lambda:'1Password')
    fake = SimpleNamespace(position=(0,0))
    plan = validate_plan({'title':'Hover','actions':[{'kind':'move','x':500,'y':500}]})
    with pytest.raises(PermissionError):
        asyncio.run(DriveController().run(plan,shot,mouse=fake,keyboard=object()))
    assert fake.position == (0,0)


def test_click_actuates_only_the_injected_fake_mouse(monkeypatch, shot):
    import tutor
    monkeypatch.setattr(tutor,'active_window_title',lambda:'Synthetic test')
    class FakeMouse:
        position=(0,0)
        def __init__(self): self.events=[]
        def press(self,button): self.events.append(('down',button))
        def release(self,button): self.events.append(('up',button))
    mouse = FakeMouse()
    plan = validate_plan({'title':'Click','actions':[{'kind':'click','x':500,'y':500}]})
    asyncio.run(DriveController().run(plan,shot,mouse=mouse,keyboard=object()))
    assert mouse.position == (-1280,800)
    assert [row[0] for row in mouse.events] == ['down','up']


def test_target_is_revealed_only_when_clicky_is_foreground(monkeypatch):
    import desktop
    own = desktop.os.getpid()
    restored=[]
    context={'hwnd':123, 'pid':987, 'title':'Synthetic app'}
    monkeypatch.setattr(desktop,'foreground',lambda:{'pid':own})
    monkeypatch.setattr(desktop,'restore',lambda target:restored.append(target))
    assert desktop.prepare_target(context)
    assert restored == [context]
    monkeypatch.setattr(desktop,'foreground',lambda:{'pid':456})
    assert not desktop.prepare_target(context)
    assert restored == [context]


def test_missing_target_never_restores_an_arbitrary_window(monkeypatch):
    import desktop
    monkeypatch.setattr(desktop,'foreground',lambda:{'pid':desktop.os.getpid()})
    monkeypatch.setattr(desktop,'restore',lambda target:pytest.fail('unexpected focus'))
    with pytest.raises(OSError): desktop.prepare_target({})
