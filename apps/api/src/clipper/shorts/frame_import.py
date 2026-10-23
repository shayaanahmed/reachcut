"""Read the declarative T=[{name,s,desc,scenes:[{n,d,c,v,g}]}] HTML format.

Only literal values are parsed. Uploaded JavaScript is never evaluated.
"""

import ast
import hashlib
import html
import json
import re
from html.parser import HTMLParser
from typing import Any


class Source(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.kind = ""
        self.styles: list[str] = []
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"style", "script"}:
            self.kind = tag

    def handle_endtag(self, tag: str) -> None:
        if tag == self.kind:
            self.kind = ""

    def handle_data(self, data: str) -> None:
        if self.kind == "style":
            self.styles.append(data)
        elif self.kind == "script":
            self.scripts.append(data)


class LiteralReader:
    def __init__(self, source: str):
        self.source = source
        self.pos = 0

    def space(self) -> None:
        while self.pos < len(self.source) and self.source[self.pos].isspace():
            self.pos += 1

    def value(self, depth: int = 0) -> Any:
        if depth > 20:
            raise ValueError("Frame data is nested too deeply")
        self.space()
        ch = self.source[self.pos : self.pos + 1]
        if ch in ('"', "'", "`"):
            start = self.pos
            self.pos += 1
            while self.pos < len(self.source):
                if self.source[self.pos] == "\\":
                    self.pos += 2
                    continue
                if self.source[self.pos] == ch:
                    self.pos += 1
                    raw = self.source[start : self.pos]
                    if ch == "`":
                        if "${" in raw:
                            raise ValueError(
                                "Template expressions are unsupported; use literal HTML"
                            )
                        return raw[1:-1].replace("\\`", "`")
                    try:
                        return ast.literal_eval(raw)
                    except (SyntaxError, ValueError) as error:
                        raise ValueError("Invalid quoted string in frame data") from error
                self.pos += 1
            raise ValueError("Unterminated string in frame data")
        if ch in ("[", "{"):
            self.pos += 1
            result: Any = [] if ch == "[" else {}
            end = "]" if ch == "[" else "}"
            while True:
                self.space()
                if self.source[self.pos : self.pos + 1] == end:
                    self.pos += 1
                    return result
                if ch == "{":
                    key = re.match(r"[A-Za-z_]\w*", self.source[self.pos :])
                    if key:
                        self.pos += len(key[0])
                        name = key[0]
                    else:
                        name = self.value(depth + 1)
                    self.space()
                    if self.source[self.pos : self.pos + 1] != ":":
                        raise ValueError("Expected a literal property in frame data")
                    self.pos += 1
                    result[name] = self.value(depth + 1)
                else:
                    result.append(self.value(depth + 1))
                self.space()
                if self.source[self.pos : self.pos + 1] == ",":
                    self.pos += 1
                elif self.source[self.pos : self.pos + 1] != end:
                    raise ValueError("Only literal arrays and objects are supported")
        number = re.match(r"-?\d+(?:\.\d+)?", self.source[self.pos :])
        if number:
            self.pos += len(number[0])
            return float(number[0])
        raise ValueError("Unsupported expression in frame data")


class Markup(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.bindings: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in {
            "div",
            "span",
            "b",
            "i",
            "strong",
            "em",
            "br",
            "p",
            "svg",
            "path",
            "g",
            "text",
            "circle",
            "rect",
            "line",
            "polyline",
        }:
            raise ValueError(f"Unsupported frame element: {tag}")
        safe = []
        for key, value in attrs:
            if key.startswith("on") or key in {"href", "src", "srcdoc"}:
                raise ValueError("Active content is unsupported in imported frames")
            if value and re.search(r"url\s*\(|javascript:|</style", value, re.I):
                raise ValueError("External resources are unsupported in imported frames")
            safe.append(f' {key}="{html.escape(value or "", quote=True)}"')
        self.parts.append(f"<{tag}{''.join(safe)}>")

    def handle_endtag(self, tag: str) -> None:
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not data.strip():
            self.parts.append(html.escape(data))
            return
        index = len(self.bindings)
        fields = [
            "title",
            "eyebrow",
            "items.0.title",
            "items.0.body",
            "items.1.title",
            "items.1.body",
            "items.2.title",
            "items.2.body",
        ]
        field = fields[index] if index < len(fields) else "unused"
        self.bindings.append((f'[data-copy="{index}"]', field))
        self.parts.append(f'<span data-copy="{index}">{html.escape(data)}</span>')


def parse_frame_html(document: str) -> dict[str, Any]:
    if len(document.encode()) > 2 * 1024 * 1024:
        raise ValueError("HTML files must be smaller than 2 MB")
    source = Source()
    source.feed(document)
    css = "\n".join(source.styles)
    if not css or re.search(r"@import|url\s*\(|</style", css, re.I):
        raise ValueError("Use embedded CSS without external resources")
    match = re.search(r"\bconst\s+T\s*=\s*(\[)", "\n".join(source.scripts))
    if not match:
        raise ValueError(
            "No frame sequences found. Expected const T=[{name,s,desc,scenes:[{n,d,c,v,g}]}]"
        )
    templates = LiteralReader(match.string[match.start(1) :]).value()
    if not isinstance(templates, list) or not 1 <= len(templates) <= 30:
        raise ValueError("Provide between 1 and 30 sequences")
    frames, sequences = [], []
    for template in templates:
        if not isinstance(template, dict) or not isinstance(template.get("scenes"), list):
            raise ValueError("Each sequence needs a name, style and scenes")
        if not isinstance(template.get("name"), str) or not template["name"].strip():
            raise ValueError("Each sequence needs a nonempty name")
        if not isinstance(template.get("s"), str):
            raise ValueError("Each sequence needs an inline style in its s field")
        # The editor supports five-scene imported stories and six-scene layouts.
        if not 5 <= len(template["scenes"]) <= 6:
            raise ValueError("Each sequence must contain five or six scenes")
        key = (
            "html-"
            + hashlib.sha256(
                json.dumps({"template": template, "css": css}, sort_keys=True).encode()
            ).hexdigest()[:16]
        )
        ids, durations = [], []
        for i, scene in enumerate(template["scenes"]):
            try:
                name, caption, markup = (str(scene[k]) for k in ("n", "c", "g"))
                duration = float(scene["d"])
                style = str(template["s"])
                if (
                    not 1 <= duration <= 15
                    or not name
                    or len(name) > 65
                    or not 1 <= len(caption) <= 90
                ):
                    raise ValueError("Invalid scene name, caption or duration")
                if re.search(r"url\s*\(|javascript:|</style", style, re.I):
                    raise ValueError("Unsupported style resource")
                clean = Markup()
                clean.feed(markup)
            except (KeyError, TypeError) as error:
                raise ValueError("Scenes require n, d, c and g fields") from error
            frame_id = f"{key}-{i + 1}"
            ids.append(frame_id)
            durations.append(duration)
            frames.append(
                dict(
                    id=frame_id,
                    volume=2,
                    name=name,
                    description=f"{template['name']} · {name}",
                    use="Hook"
                    if i == 0
                    else "Closing"
                    if i == len(template["scenes"]) - 1
                    else "Explain",
                    caption=caption,
                    duration_seconds=duration,
                    style=style,
                    markup="".join(clean.parts),
                    css=css,
                    bindings=clean.bindings,
                    voiceover=str(scene.get("v", "")),
                )
            )
        sequences.append(
            dict(
                id=key,
                name=str(template["name"]),
                description=str(template.get("desc", "")),
                background="#101114",
                accent="#0a84ff",
                secondary="#eceef2",
                font="Space Grotesk",
                frames=ids,
                durations=durations,
                theme="neon",
            )
        )
    return {"frames": frames, "sequences": sequences}
