"""Render the supplied frame designs with their original HTML, CSS and animation."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image

from clipper.shorts.frames import FrameContent, FrameSequence, design_catalogue

ROOT = Path(__file__).parent / "assets/frames/library"

# Selectors bind real story content into the supplied layouts. Sample previews
# retain the author's placeholder copy; production never inherits sample claims.
BINDINGS: dict[str, list[tuple[str, str]]] = {
    "shortcut-keycaps": [
        (".key:nth-child(1)", "items.0.title"),
        (".key:nth-child(3)", "items.1.title"),
        (".a:nth-child(2)", "title"),
        (".a:nth-child(3)", "eyebrow"),
    ],
    "command-palette": [
        (".type", "title"),
        (".pop:nth-child(2)>span:first-child", "items.0.body"),
        (".pop:nth-child(3)", "items.1.body"),
        (".pop:nth-child(4)", "items.2.body"),
    ],
    "error-to-fix": [(".sk", "items.0.body"), (".type", "items.1.body"), (".pop", "items.2.body")],
    "settings-toggles": [
        (".a:first-child", "title"),
        (".a:nth-child(2)>div:nth-child(1)::text", "items.0.title"),
        (".a:nth-child(2)>div:nth-child(2)::text", "items.1.title"),
        (".a:nth-child(2)>div:nth-child(3)::text", "items.2.title"),
    ],
    "sticky-note": [
        (".rot>.pop:nth-child(2)", "eyebrow"),
        (".rot>.pop:nth-child(3)", "title"),
        (".rot>.pop:nth-child(4)", "items.0.body"),
    ],
    "hand-drawn": [
        ("svg text:nth-child(1)", "items.0.title"),
        ("svg text:nth-child(2)", "items.1.title"),
        ("svg text:nth-child(3)", "items.2.title"),
    ],
    "stock-ticker": [
        (".mq>span", "eyebrow"),
        (".a:nth-child(2)>div:first-child", "title"),
        (".a:nth-child(2)>div:nth-child(2)", "items.0.title"),
        (".a:nth-child(2)>div:nth-child(3)", "items.0.body"),
    ],
    "game-hud": [
        (".a:first-child>span:last-child", "eyebrow"),
        (".slam", "title"),
        (".a:nth-child(3)>.ctr", "items.0.title"),
        (".sl>div:first-child", "items.1.title"),
        (".sl>div:last-child", "items.1.body"),
    ],
    "comment-section": [
        (".a:first-child", "title"),
        (".a:nth-child(2)>.sl:nth-child(1)>div>div", "items.0.title"),
        (".a:nth-child(2)>.sl:nth-child(2)>div>div", "items.1.title"),
        (".a:nth-child(2)>.sl:nth-child(3)>div>div", "items.2.title"),
        (".a:nth-child(2)>.sl:nth-child(1)>div::text", "items.0.body"),
        (".a:nth-child(2)>.sl:nth-child(2)>div::text", "items.1.body"),
        (".a:nth-child(2)>.sl:nth-child(3)>div::text", "items.2.body"),
    ],
    "do-dont": [
        (".a:first-child>.mono", "items.0.body"),
        (".a:nth-child(2)>.mono", "items.1.body"),
    ],
    "browser-window": [
        (".a>div:first-child>span", "eyebrow"),
        (".type", "items.0.body"),
        (".a>div:nth-child(3)>.pop:first-child", "title"),
        (".a>div:nth-child(3)>.pop:last-child", "items.1.title"),
    ],
    "copy-command": [
        (".badge", "eyebrow"),
        (".type", "items.0.body"),
        (".a:nth-child(3)", "items.1.body"),
        (".a:nth-child(4)", "items.2.body"),
    ],
    "before-after": [
        (".card>div:first-child>div:first-child", "items.0.title"),
        (".card>div:first-child>div:last-child", "items.0.body"),
        (".wipe>div:first-child", "items.1.title"),
        (".wipe>div:last-child", "items.1.body"),
    ],
    "versus": [
        (".card:nth-child(1)>div:nth-child(2)", "items.0.title"),
        (".card:nth-child(1)>div:nth-child(3)", "items.0.body"),
        (".card:nth-child(3)>div:nth-child(2)", "items.1.title"),
        (".card:nth-child(3)>div:nth-child(3)", "items.1.body"),
    ],
    "leaderboard": [
        (".a.mut", "title"),
        (".row:nth-child(1)::text", "items.0.title"),
        (".row:nth-child(2)::text", "items.1.title"),
        (".row:nth-child(3)::text", "items.2.title"),
    ],
    "code-diff": [
        (".card>.mut", "eyebrow"),
        (".del", "items.0.body"),
        (".add", "items.1.body"),
        (".badge", "items.2.title"),
    ],
    "language-bar": [(".card>.mut", "title"), (".card>.pop", "items.0.body")],
    "notifications": [
        (".rows>.card:nth-child(1)", "items.0.body"),
        (".rows>.card:nth-child(2)", "items.1.body"),
        (".rows>.card:nth-child(3)", "items.2.body"),
    ],
    "contributors": [(".av:last-child", "items.0.body"), (".a>.mut", "title")],
    "timeline": [
        (".a.mut", "title"),
        (".rows>.pop:nth-child(1)>span", "items.0.body"),
        (".rows>.pop:nth-child(2)>span", "items.1.body"),
        (".rows>.pop:nth-child(3)>span", "items.2.body"),
    ],
    "hot-take": [(".badge", "eyebrow"), (".ctr>.pop:last-child", "title")],
    "build-progress": [
        (".card>div:first-child>span:first-child", "title"),
        ("[data-to]", "items.0.body"),
        (".card>.pop", "items.1.body"),
    ],
    "file-tree": [
        (".card>.type:nth-child(1)", "title"),
        (".card>.type:nth-child(2)", "items.0.body"),
        (".card>.type:nth-child(3)", "items.1.body"),
        (".card>.type:nth-child(4)", "items.2.body"),
        (".badge", "eyebrow"),
    ],
    "speed-dial": [("[data-to]", "items.0.body"), (".ctr>.mut", "title")],
    "kinetic-poster": [
        (".slam:nth-child(1)", "items.0.title"),
        (".slam:nth-child(2)", "items.1.title"),
        (".slam:nth-child(3)", "items.2.title"),
    ],
    "newspaper": [
        (".ctr", "eyebrow"),
        (".pop:nth-of-type(3)", "title"),
        (".pop.mut", "items.0.body"),
    ],
    "chat-thread": [
        (".a.ctr", "eyebrow"),
        (".sl:nth-child(1)", "items.0.body"),
        (".sl:nth-child(2)", "items.1.body"),
    ],
    "code-editor": [
        (".mono>div:first-child>span", "eyebrow"),
        (".type:nth-of-type(1)", "items.0.body"),
    ],
    "retro-crt": [
        (".type:nth-child(1)", "items.0.body"),
        (".type:nth-child(2)", "items.1.body"),
        (".type:nth-child(3)", "items.2.body"),
    ],
    "trading-card": [
        (".flip>div>div:first-child>span:first-child", "title"),
        (".flip>div>div:first-child>span:last-child", "eyebrow"),
        (".flip>div>div:last-child>span:nth-of-type(1)", "items.0.title"),
        (".flip>div>div:last-child>span:nth-of-type(2)", "items.1.title"),
        (".flip>div>div:last-child>span:nth-of-type(3)", "items.2.title"),
    ],
    "receipt": [
        (".mono>div:first-child>.ctr:first-child", "title"),
        (".mono>div:first-child>.ctr:nth-child(2)", "eyebrow"),
        (".mono .pop:nth-of-type(3)>span:first-child", "items.0.title"),
        (".mono .pop:nth-of-type(3)>span:last-child", "items.0.body"),
        (".mono .pop:nth-of-type(4)>span:first-child", "items.1.title"),
        (".mono .pop:nth-of-type(4)>span:last-child", "items.1.body"),
        (".mono .pop:nth-of-type(5)>span:first-child", "items.2.title"),
        (".mono .pop:nth-of-type(5)>span:last-child", "items.2.body"),
        (".mono .pop:last-child>span:last-child", "items.2.body"),
        (".rot", "items.2.title"),
    ],
    "blueprint": [
        ("svg text:nth-child(1)", "items.0.title"),
        ("svg text:nth-child(2)", "items.1.title"),
        ("svg text:nth-child(3)", "items.2.title"),
    ],
    "sticker-pack": [
        (".rot:nth-child(1)", "items.0.title"),
        (".rot:nth-child(2)", "items.1.title"),
        (".rot:nth-child(3)", "items.2.title"),
    ],
    "pull-request": [
        (".a>div:first-child", "title"),
        (".pop>span:last-child", "items.0.body"),
        (".pop.mono", "items.1.body"),
        (".pop:last-child>div:first-child", "eyebrow"),
        (".pop:last-child>div:last-child", "items.2.body"),
    ],
    "story-poll": [
        (".a>div:first-child", "title"),
        (".a>div:nth-child(2)>div>span:first-child", "items.0.title"),
        (".a>div:nth-child(3)>div>span:first-child", "items.1.title"),
    ],
    "bento-stats": [
        (".a>div:nth-child(1)>div:first-child", "items.0.title"),
        (".a>div:nth-child(1)>div:last-child", "items.0.body"),
        (".a>div:nth-child(2)>div:first-child", "items.1.title"),
        (".a>div:nth-child(2)>div:last-child", "items.1.body"),
        (".a>div:nth-child(3)>div:first-child", "items.2.title"),
        (".a>div:nth-child(3)>div:last-child", "items.2.body"),
        (".a>div:nth-child(4)", "eyebrow"),
    ],
}


def is_html_frame(content: FrameContent) -> bool:
    return content.template in BINDINGS or any(
        d["id"] == content.template for d in design_catalogue()
    )


def frame_document(content: FrameContent, sequence: FrameSequence, *, sample: bool = False) -> str:
    design = next((d for d in design_catalogue() if d["id"] == content.template), None)
    if design is None:
        design = next(
            d
            for d in json.loads((ROOT / "legacy-catalogue.json").read_text())
            if d["id"] == content.template
        )
    css = str(design.get("css") or (ROOT / f"volume-{design['volume']}.css").read_text())
    engine = (ROOT / "player.js").read_text()
    data = (
        json.dumps(
            {
                "design": design,
                "content": content.model_dump(),
                "theme": sequence.theme,
                "sample": sample,
                "bindings": design.get("bindings", BINDINGS.get(content.template, [])),
            }
        )
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<style>{css}</style><style>"
        "html,body{margin:0;padding:0;width:100%;height:100%;max-width:none;overflow:hidden}"
        "#viewport{width:270px;transform-origin:top left;container-type:inline-size}"
        "#grid{display:block;width:270px}figure{container-type:inline-size;margin:0}"
        ".st{width:270px;height:480px;aspect-ratio:auto;box-sizing:border-box}"
        ".type{max-width:100%}.bound{overflow-wrap:normal;word-break:normal}"
        ".cp{color:var(--caption-fg,var(--fg))}"
        "</style></head><body><div id=viewport><main id=grid><figure>"
        '<div class="st play" tabindex="0" role="button" aria-label="Replay frame"></div>'
        f"</figure></main></div><script>(() => {{const DATA={data};\n{engine}\n}})();"
        "</script></body></html>"
    )


class HTMLFramePainter:
    """One isolated browser per rendering session, reused for every video frame."""

    def __init__(self, content: FrameContent, sequence: FrameSequence, *, sample: bool = False):
        self.document = frame_document(content, sequence, sample=sample)
        self.runtime: Any = None
        self.browser: Any = None
        self.page: Any = None

    def __enter__(self) -> "HTMLFramePainter":
        from playwright.sync_api import sync_playwright

        self.runtime = sync_playwright().start()
        try:
            self.browser = self.runtime.chromium.launch(headless=True)
            self.page = self.browser.new_page(
                viewport={"width": 270, "height": 480}, device_scale_factor=2
            )
            self.page.route("**/*", lambda route: route.abort())
            self.page.set_content(self.document, wait_until="load")
            self.page.wait_for_function("window.renderAt && document.querySelector('.cp')")
            self.page.evaluate("document.fonts.ready")
            return self
        except BaseException:
            self.__exit__()
            raise

    def __exit__(self, *_args: object) -> None:
        if self.browser:
            self.browser.close()
        if self.runtime:
            self.runtime.stop()

    def frame(self, local: float, duration: float, progress: float = 0) -> Image.Image:
        import io

        self.page.evaluate("t => window.renderAt(t)", local * 5 / max(duration, 0.1))
        return Image.open(io.BytesIO(self.page.screenshot())).convert("RGB")

    def issues(self) -> list[str]:
        self.page.evaluate("window.renderAt(5)")
        return list(self.page.evaluate("window.layoutIssues()"))


@lru_cache(maxsize=256)
def validate_html_layout(content_json: str, sequence_json: str) -> list[str]:
    with HTMLFramePainter(
        FrameContent.model_validate_json(content_json),
        FrameSequence.model_validate_json(sequence_json),
    ) as painter:
        return painter.issues()
