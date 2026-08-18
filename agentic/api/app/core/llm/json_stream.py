from __future__ import annotations

from dataclasses import dataclass


class JSONProjectionError(ValueError):
    """增量内容已能确定违反安全投影契约。"""


@dataclass(frozen=True, slots=True)
class _StringResult:
    value: str
    end: int | None


@dataclass(frozen=True, slots=True)
class _ProjectionResult:
    value: str = ""
    started: bool = False
    complete: bool = False


class TopLevelJSONStringProjector:
    """只解码一个代码指定的顶层 JSON 字符串字段。"""

    def __init__(self, field: str) -> None:
        if not field:
            raise ValueError("投影字段不能为空")
        self._field = field
        self._buffer = ""
        self._emitted = ""
        self._started = False
        self._complete = False

    @property
    def started(self) -> bool:
        return self._started

    @property
    def complete(self) -> bool:
        return self._complete

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        self._buffer += chunk
        result = _extract_top_level_string(self._buffer, self._field)
        if not result.value.startswith(self._emitted):
            raise JSONProjectionError("增量 JSON 字符串前缀发生回退")
        delta = result.value[len(self._emitted):]
        self._emitted = result.value
        self._started = result.started
        self._complete = result.complete
        return delta

    def reset(self) -> None:
        self._buffer = ""
        self._emitted = ""
        self._started = False
        self._complete = False


def _extract_top_level_string(payload: str, field: str) -> _ProjectionResult:
    index = _skip_whitespace(payload, 0)
    if index >= len(payload) or payload[index] != "{":
        return _ProjectionResult()
    index += 1

    while True:
        index = _skip_whitespace(payload, index)
        if index >= len(payload) or payload[index] == "}":
            return _ProjectionResult()
        if payload[index] != '"':
            raise JSONProjectionError("顶层 JSON 对象的字段名必须是字符串")

        key = _decode_string(payload, index)
        if key.end is None:
            return _ProjectionResult()
        index = _skip_whitespace(payload, key.end)
        if index >= len(payload):
            return _ProjectionResult()
        if payload[index] != ":":
            raise JSONProjectionError("顶层 JSON 字段缺少冒号")
        index = _skip_whitespace(payload, index + 1)
        if index >= len(payload):
            return _ProjectionResult()

        if key.value == field:
            if payload[index] != '"':
                raise JSONProjectionError(f"顶层字段 {field} 必须是字符串")
            value = _decode_string(payload, index)
            return _ProjectionResult(
                value=value.value,
                started=True,
                complete=value.end is not None,
            )

        value_end = _skip_value(payload, index)
        if value_end is None:
            return _ProjectionResult()
        index = _skip_whitespace(payload, value_end)
        if index >= len(payload):
            return _ProjectionResult()
        if payload[index] == ",":
            index += 1
            continue
        if payload[index] == "}":
            return _ProjectionResult()
        raise JSONProjectionError("顶层 JSON 字段之间缺少逗号")


def _skip_whitespace(payload: str, index: int) -> int:
    while index < len(payload) and payload[index] in " \t\r\n":
        index += 1
    return index


def _decode_string(payload: str, start: int) -> _StringResult:
    if start >= len(payload) or payload[start] != '"':
        raise JSONProjectionError("JSON 字符串必须以引号开始")

    decoded: list[str] = []
    index = start + 1
    simple_escapes = {
        '"': '"',
        "\\": "\\",
        "/": "/",
        "b": "\b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "t": "\t",
    }
    while index < len(payload):
        char = payload[index]
        if char == '"':
            return _StringResult("".join(decoded), index + 1)
        if ord(char) < 0x20:
            raise JSONProjectionError("JSON 字符串包含未转义控制字符")
        if char != "\\":
            decoded.append(char)
            index += 1
            continue

        if index + 1 >= len(payload):
            return _StringResult("".join(decoded), None)
        escape = payload[index + 1]
        if escape in simple_escapes:
            decoded.append(simple_escapes[escape])
            index += 2
            continue
        if escape != "u":
            raise JSONProjectionError(f"不支持的 JSON 转义: \\{escape}")
        if index + 6 > len(payload):
            return _StringResult("".join(decoded), None)

        code_unit = _parse_hex(payload[index + 2:index + 6])
        next_index = index + 6
        if 0xD800 <= code_unit <= 0xDBFF:
            if next_index + 2 > len(payload):
                return _StringResult("".join(decoded), None)
            if payload[next_index:next_index + 2] != "\\u":
                raise JSONProjectionError("高位代理项后缺少低位代理项")
            if next_index + 6 > len(payload):
                return _StringResult("".join(decoded), None)
            low = _parse_hex(payload[next_index + 2:next_index + 6])
            if not 0xDC00 <= low <= 0xDFFF:
                raise JSONProjectionError("Unicode 代理对无效")
            codepoint = 0x10000 + ((code_unit - 0xD800) << 10) + (low - 0xDC00)
            decoded.append(chr(codepoint))
            index = next_index + 6
            continue
        if 0xDC00 <= code_unit <= 0xDFFF:
            raise JSONProjectionError("Unicode 低位代理项缺少高位代理项")
        decoded.append(chr(code_unit))
        index = next_index

    return _StringResult("".join(decoded), None)


def _parse_hex(value: str) -> int:
    if len(value) != 4 or any(char not in "0123456789abcdefABCDEF" for char in value):
        raise JSONProjectionError("Unicode 转义必须包含四位十六进制字符")
    return int(value, 16)


def _skip_value(payload: str, start: int) -> int | None:
    if start >= len(payload):
        return None
    if payload[start] == '"':
        return _decode_string(payload, start).end
    if payload[start] not in "{[":
        index = start
        while index < len(payload) and payload[index] not in ",} \t\r\n":
            index += 1
        return index if index < len(payload) else None

    expected_closers = ["}" if payload[start] == "{" else "]"]
    index = start + 1
    in_string = False
    escaped = False
    while index < len(payload):
        char = payload[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            expected_closers.append("}")
        elif char == "[":
            expected_closers.append("]")
        elif char in "}]":
            if not expected_closers or char != expected_closers[-1]:
                raise JSONProjectionError("嵌套 JSON 括号不匹配")
            expected_closers.pop()
            if not expected_closers:
                return index + 1
        index += 1
    return None

