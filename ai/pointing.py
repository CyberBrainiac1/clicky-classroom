"""Same-request UIA/OCR, Claude and grid fallback for the blue teaching guide."""
import asyncio
import logging
import math

from ai import element_locator, hybrid_pointer, universal_locator

_log = logging.getLogger("clicky.pointing")


def _inside(shot, x, y):
    return (all(type(v) in (int, float) and math.isfinite(v) for v in (x, y))
            and shot.logical_left <= x <= shot.logical_left + (shot.physical_width - 1) / shot.dpi_scale
            and shot.logical_top <= y <= shot.logical_top + (shot.physical_height - 1) / shot.dpi_scale)


async def locate_target(*, shot, query, llm, model=None, claude_model=None, window_handle=None):
    """Suggestions only. A miss or exception tries the next tier in this request."""
    if not math.isfinite(shot.dpi_scale) or shot.dpi_scale <= 0:
        return None
    try:
        target = await asyncio.wait_for(asyncio.to_thread(
            hybrid_pointer.find_target, query, screenshot=shot, skip_vision=True,
            window_handle=window_handle), timeout=3)
        if target is not None and target.source in ("uia", "ocr"):
            x = shot.logical_left + (target.x - shot.physical_left) / shot.dpi_scale
            y = shot.logical_top + (target.y - shot.physical_top) / shot.dpi_scale
            if _inside(shot, x, y):
                return element_locator.Detected(round(x), round(y), shot.index)
    except Exception as exc:
        _log.info("Local pointer missed (%s); trying vision", type(exc).__name__)
    options = dict(screenshot_jpeg_b64=shot.base64_jpeg,
                   original_width=shot.width, original_height=shot.height,
                   screen_index=shot.index, user_question=query,
                   physical_width=shot.physical_width, physical_height=shot.physical_height,
                   physical_left=shot.physical_left, physical_top=shot.physical_top,
                   logical_left=shot.logical_left, logical_top=shot.logical_top,
                   dpi_scale=shot.dpi_scale)
    if element_locator.is_available(claude_model):
        try:
            target = await asyncio.wait_for(element_locator.detect_element(
                **options, model=claude_model), timeout=12)
            if target is not None and _inside(shot, target.x, target.y):
                return target
        except Exception as exc:
            _log.info("Claude pointer missed (%s); trying grid", type(exc).__name__)
    try:
        target = await asyncio.wait_for(universal_locator.detect_element_universal(
            **options, llm=llm, model=model), timeout=16)
        if target is not None and _inside(shot, target.x, target.y):
            return target
    except Exception as exc:
        _log.info("Grid pointer missed (%s)", type(exc).__name__)
    _log.info("No visible target found after all available pointer tiers")
    return None
