#!/usr/bin/env python3
"""dev 원고에서 주석을 걷어내 main 인쇄본을 만드는 도구.

언어별로 "주석만" 지우고, 지운 뒤에는 원본과 결과가 같은 코드인지 독립 파서로
확인한다(파이썬 AST, YAML 로드값, XML 트리, gcc 전처리). 확인에 실패한 파일은
건드리지 않고 이름을 보고한다.
"""
import ast
import io
import re
import tokenize

PY_KEEP = re.compile(
    r"^#\s*(!|-\*-|coding[:=]|noqa\b|type:|pylint|pragma\b|fmt:|isort:|nosec\b|mypy:)",
    re.I,
)

_DOC_RE = re.compile(r"^([rRuU]?)(\"\"\"|''')(.*)\2$", re.S)
_DOC_HOLDERS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def _newline_of(src):
    """줄끝이 전부 CRLF 일 때만 CRLF 를 지킨다. 섞여 있으면 LF 로 통일한다."""
    crlf = src.count("\r\n")
    return "\r\n" if crlf and crlf == src.count("\n") else "\n"


def _docstring_nodes(tree):
    for node in ast.walk(tree):
        if not isinstance(node, _DOC_HOLDERS) or not node.body:
            continue
        first = node.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            yield first.value


def first_line(text):
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _truncate_docstrings(src):
    tree = ast.parse(src)
    blines = src.encode("utf-8").splitlines(keepends=True)
    nodes = sorted(
        _docstring_nodes(tree), key=lambda n: (n.lineno, n.col_offset), reverse=True
    )
    for n in nodes:
        if n.end_lineno == n.lineno:
            continue
        head = blines[n.lineno - 1][: n.col_offset]
        tail = blines[n.end_lineno - 1][n.end_col_offset :]
        raw = b"".join(
            [blines[n.lineno - 1][n.col_offset :]]
            + blines[n.lineno : n.end_lineno - 1]
            + [blines[n.end_lineno - 1][: n.end_col_offset]]
        ).decode("utf-8")
        m = _DOC_RE.match(raw)
        if not m:
            continue
        prefix, quote, body = m.groups()
        if quote in body:
            continue
        fl = first_line(body)
        if not fl or fl.endswith("\\"):
            continue
        q = '"""'
        if '"""' in fl or fl.endswith('"'):
            if "'''" in fl or fl.endswith("'"):
                continue
            q = "'''"
        new = f"{prefix}{q}{fl}{q}".encode("utf-8")
        blines[n.lineno - 1 : n.end_lineno] = [head + new + tail]
    return b"".join(blines).decode("utf-8")


def _cleanup(lines, protected, delete, max_blank, newline):
    kept = []
    for i, line in enumerate(lines, 1):
        if i in delete:
            continue
        body = line.rstrip("\r\n")
        if i not in protected:
            body = body.rstrip()
        kept.append((i, body))
    result = []
    j, n = 0, len(kept)
    while j < n:
        row, body = kept[j]
        if body == "" and row not in protected:
            k = j
            while k < n and kept[k][1] == "" and kept[k][0] not in protected:
                k += 1
            if k < n and result:
                result.extend([""] * min(k - j, max_blank(kept[k][1])))
            j = k
        else:
            result.append(body)
            j += 1
    return newline.join(result) + (newline if result else "")


def _py_max_blank(next_line):
    return 1 if next_line[:1].isspace() else 2


def _strip_py_comments(src):
    lines = src.splitlines(keepends=True)
    protected, delete = set(), set()
    for t in tokenize.generate_tokens(io.StringIO(src).readline):
        if t.type == tokenize.STRING and t.end[0] > t.start[0]:
            protected.update(range(t.start[0], t.end[0] + 1))
        elif t.type == tokenize.COMMENT and not PY_KEEP.match(t.string):
            row, col = t.start
            line = lines[row - 1]
            head = line[:col].rstrip()
            if head == "":
                delete.add(row)
            else:
                lines[row - 1] = head + line[len(line.rstrip("\r\n")) :]
    return _cleanup(lines, protected, delete, _py_max_blank, _newline_of(src))


def strip_python(src):
    return _strip_py_comments(_truncate_docstrings(src))


def _normalized_python(src):
    tree = ast.parse(src)
    docs = []
    for node in _docstring_nodes(tree):
        docs.append(node.value)
        node.value = ""
    return ast.dump(tree), docs


def _in_spans(spans, row, col):
    for sl, sc, el, ec in spans:
        if (sl, sc) <= (row, col) < (el, ec):
            return True
    return False


def _hash_comment_start(line, row, spans, keep_dollar=False):
    for i, ch in enumerate(line):
        if ch != "#" or _in_spans(spans, row, i):
            continue
        if i == 0 or line[i - 1] in " \t":
            return i
    return None


def _apply_hash_removals(lines, spans, keep):
    delete = set()
    for idx, line in enumerate(lines):
        if keep(line):
            continue
        i = _hash_comment_start(line, idx, spans)
        if i is None:
            continue
        head = line[:i].rstrip()
        if head == "":
            delete.add(idx + 1)
        else:
            lines[idx] = head + line[len(line.rstrip("\r\n")) :]
    return delete


def strip_yaml(src):
    import yaml

    lines = src.splitlines(keepends=True)
    spans, protected = [], set()
    for tok in yaml.scan(src):
        if not isinstance(tok, yaml.ScalarToken):
            continue
        s, e = tok.start_mark, tok.end_mark
        spans.append((s.line, s.column, e.line, e.column))
        if e.line <= s.line:
            continue
        if tok.style in ("|", ">"):
            indicator = re.match(r"[|>][0-9+-]*", lines[s.line][s.column :])
            last = e.line - 1
            if "+" not in indicator.group():
                while last > s.line and lines[last].strip() == "":
                    last -= 1
            protected.update(range(s.line + 2, last + 2))
        else:
            protected.update(range(s.line + 1, e.line + 2))
    delete = _apply_hash_removals(lines, spans, lambda line: False)
    return _cleanup(lines, protected, delete, lambda _: 1, _newline_of(src))


def verify_yaml(orig, new):
    import yaml

    try:
        return list(yaml.safe_load_all(orig)) == list(yaml.safe_load_all(new))
    except yaml.YAMLError:
        return False


_XML_COMMENT = re.compile(r"<!--.*?-->", re.S)


def strip_xml(src):
    for m in reversed(list(_XML_COMMENT.finditer(src))):
        s, e = m.span()
        line_start = src.rfind("\n", 0, s) + 1
        line_end = src.find("\n", e)
        if line_end == -1:
            line_end = len(src)
        if src[line_start:s].strip() == "" and src[e:line_end].strip() == "":
            src = src[:line_start] + src[line_end + 1 :]
        else:
            src = src[:s] + src[e:]
    lines = src.splitlines(keepends=True)
    return _cleanup(lines, set(), set(), lambda _: 1, _newline_of(src))


def _xml_canonical(src):
    from lxml import etree

    parser = etree.XMLParser(remove_comments=True, remove_blank_text=True)
    root = etree.fromstring(src.encode("utf-8"), parser)
    return etree.tostring(root.getroottree(), method="c14n")


def verify_xml(orig, new):
    try:
        return _xml_canonical(orig) == _xml_canonical(new)
    except Exception:
        return False


CLIKE_KEEP = re.compile(r"^//\s*(ignore(_for_file)?:|NOLINT|clang-format)")


def _line_offsets(src):
    offsets = [0]
    for i, ch in enumerate(src):
        if ch == "\n":
            offsets.append(i + 1)
    return offsets


def _pos(offsets, index):
    import bisect

    row = bisect.bisect_right(offsets, index) - 1
    return row + 1, index - offsets[row]


def _scan_clike(src, lang):
    """주석 구간과 여러 줄 문자열 구간을 찾아 돌려준다. 문자열·보간 안의 // 는 무시한다."""
    comments, string_spans = [], []
    stack = [["code", 0]]
    i, n = 0, len(src)
    while i < n:
        state = stack[-1]
        kind = state[0]
        ch = src[i]
        if kind == "code":
            if src.startswith("//", i):
                stack.append(["line", i])
                i += 2
            elif src.startswith("/*", i):
                stack.append(["block", i])
                i += 2
            elif ch == "{" and len(stack) > 1:
                state[1] += 1
                i += 1
            elif ch == "}" and len(stack) > 1:
                if state[1] == 0:
                    stack.pop()
                else:
                    state[1] -= 1
                i += 1
            elif ch in "\"'":
                if (
                    lang == "cpp"
                    and ch == "'"
                    and i > 0
                    and src[i - 1].isdigit()
                    and i + 1 < n
                    and src[i + 1].isalnum()
                ):
                    i += 1
                    continue
                if lang == "cpp" and ch == '"' and i > 0 and src[i - 1] == "R":
                    close = src.index("(", i)
                    delim = ")" + src[i + 1 : close] + '"'
                    end = src.index(delim, close) + len(delim)
                    string_spans.append((i, end))
                    i = end
                    continue
                raw = lang == "dart" and i > 0 and src[i - 1] == "r" and (
                    i < 2 or not (src[i - 2].isalnum() or src[i - 2] == "_")
                )
                triple = lang == "dart" and src.startswith(ch * 3, i)
                stack.append(["str", ch, triple, raw, i])
                i += 3 if triple else 1
            else:
                i += 1
        elif kind == "str":
            _, quote, triple, raw, start = state
            if not raw and ch == "\\":
                i += 2
            elif lang == "dart" and not raw and src.startswith("${", i):
                stack.append(["code", 0])
                i += 2
            elif triple and src.startswith(quote * 3, i):
                stack.pop()
                string_spans.append((start, i + 3))
                i += 3
            elif not triple and (ch == quote or ch == "\n"):
                stack.pop()
                string_spans.append((start, i + 1))
                i += 1
            else:
                i += 1
        elif kind == "line":
            end = src.find("\n", i)
            end = n if end == -1 else end
            comments.append((state[1], end))
            stack.pop()
            i = end
        elif kind == "block":
            end = src.find("*/", i)
            end = n if end == -1 else end + 2
            comments.append((state[1], end))
            stack.pop()
            i = end
    return comments, string_spans


def _remove_spans(src, comments, string_spans, keep):
    """주석 구간을 지운다. keep(text, row, head_blank) 가 True 면 그 주석은 남긴다."""
    offsets = _line_offsets(src)
    lines = src.splitlines(keepends=True)
    protected = set()
    for s, e in string_spans:
        r1, _ = _pos(offsets, s)
        r2, _ = _pos(offsets, e - 1)
        if r2 > r1:
            protected.update(range(r1, r2 + 1))
    edits = []
    for s, e in comments:
        text = src[s:e]
        sr, sc = _pos(offsets, s)
        er, ec = _pos(offsets, e)
        if e == len(src) or src[e - 1] == "\n":
            er, ec = _pos(offsets, e - 1)
            ec += 1
        if keep(text, sr, lines[sr - 1][:sc].strip() == ""):
            continue
        edits.append((sr, sc, er, ec))
    delete = set()
    for sr, sc, er, ec in reversed(edits):
        head = lines[sr - 1][:sc]
        end_body = lines[er - 1].rstrip("\r\n")
        nl = lines[er - 1][len(end_body) :]
        tail = end_body[ec:]
        if head.strip() == "" and tail.strip() == "":
            delete.update(range(sr, er + 1))
            continue
        if head.strip() == "":
            merged = head + tail.lstrip()
        elif tail.strip() == "":
            merged = head.rstrip()
        else:
            merged = head.rstrip() + " " + tail.lstrip()
        lines[sr - 1] = merged + nl
        delete.update(range(sr + 1, er + 1))
    return _cleanup(lines, protected, delete, lambda _: 1, _newline_of(src))


def strip_clike(src, lang):
    comments, string_spans = _scan_clike(src, lang)
    last_doc_row = [None]

    def keep(text, row, head_blank):
        if CLIKE_KEEP.match(text):
            return True
        if text.startswith("///") and not text.startswith("////"):
            first_of_block = last_doc_row[0] != row - 1
            last_doc_row[0] = row
            return head_blank and first_of_block
        return False

    return _remove_spans(src, comments, string_spans, keep)


_LUA_LONG = re.compile(r"\[(=*)\[")


def _scan_lua(src):
    comments, strings = [], []
    i, n = 0, len(src)
    while i < n:
        ch = src[i]
        if src.startswith("--", i):
            m = _LUA_LONG.match(src, i + 2)
            if m:
                close = "]" + m.group(1) + "]"
                end = src.find(close, m.end())
                end = n if end == -1 else end + len(close)
            else:
                end = src.find("\n", i)
                end = n if end == -1 else end
            comments.append((i, end))
            i = end
        elif ch in "\"'":
            j = i + 1
            while j < n and src[j] not in (ch, "\n"):
                j += 2 if src[j] == "\\" else 1
            strings.append((i, j + 1))
            i = j + 1
        elif ch == "[" and _LUA_LONG.match(src, i):
            m = _LUA_LONG.match(src, i)
            close = "]" + m.group(1) + "]"
            end = src.find(close, m.end())
            end = n if end == -1 else end + len(close)
            strings.append((i, end))
            i = end
        else:
            i += 1
    return comments, strings


def strip_lua(src):
    comments, strings = _scan_lua(src)
    return _remove_spans(src, comments, strings, lambda *_: False)


SH_KEEP = re.compile(r"^#\s*(!|shellcheck)")
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def strip_shell(src):
    lines = src.splitlines(keepends=True)
    delete, protected = set(), set()
    in_single = in_double = False
    pending, active = [], None
    for idx, line in enumerate(lines):
        row = idx + 1
        body = line.rstrip("\r\n")
        nl = line[len(body) :]
        if active:
            protected.add(row)
            tag, strip_tabs = active
            if (body.lstrip("\t") if strip_tabs else body) == tag:
                active = pending.pop(0) if pending else None
            continue
        started_quoted = in_single or in_double
        if started_quoted:
            protected.add(row)
        i, comment_at = 0, None
        while i < len(body):
            ch = body[i]
            if in_single:
                if ch == "'":
                    in_single = False
            elif in_double:
                if ch == "\\":
                    i += 1
                elif ch == '"':
                    in_double = False
            elif ch == "\\":
                i += 1
            elif ch == "'":
                in_single = True
            elif ch == '"':
                in_double = True
            elif ch == "#" and (i == 0 or body[i - 1] in " \t"):
                comment_at = i
                break
            elif body.startswith("<<", i) and not body.startswith("<<<", i):
                m = _HEREDOC.match(body, i)
                if m:
                    pending.append((m.group(2), body.startswith("<<-", i)))
                    i = m.end()
                    continue
            i += 1
        if comment_at is not None and not started_quoted:
            if not SH_KEEP.match(body[comment_at:]):
                head = body[:comment_at]
                if head.strip() == "":
                    delete.add(row)
                else:
                    lines[idx] = head.rstrip() + nl
        if pending and active is None:
            active = pending.pop(0)
    return _cleanup(lines, protected, delete, lambda _: 1, _newline_of(src))


def verify_shell(orig, new):
    import subprocess

    return subprocess.run(["bash", "-n"], input=new, capture_output=True, text=True).returncode == 0


def _quote_aware_hash(body):
    in_q, i = None, 0
    while i < len(body):
        ch = body[i]
        if in_q:
            if ch == "\\":
                i += 1
            elif ch == in_q:
                in_q = None
        elif ch in "\"'":
            in_q = ch
        elif ch == "#" and (i == 0 or body[i - 1] in " \t"):
            return i
        i += 1
    return None


def strip_hash_lines(src):
    lines = src.splitlines(keepends=True)
    delete = set()
    for idx, line in enumerate(lines):
        body = line.rstrip("\r\n")
        if body.startswith("#!"):
            continue
        i = _quote_aware_hash(body)
        if i is None:
            continue
        head = body[:i]
        if head.strip() == "":
            delete.add(idx + 1)
        else:
            lines[idx] = head.rstrip() + line[len(body) :]
    return _cleanup(lines, set(), delete, lambda _: 1, _newline_of(src))


def _spec_key(spec):
    fields = [(str(f.type), f.name, f.default_value) for f in spec.fields]
    constants = [(str(c.type), c.name, c.value) for c in spec.constants]
    return fields, constants


def verify_interface(name, orig, new):
    """rosidl 파서로 필드·상수를 비교한다. ROS 환경이 없으면 None(판정 불가)."""
    try:
        from rosidl_adapter import parser
    except ImportError:
        return None
    stem, ext = name.rsplit("/", 1)[-1].rsplit(".", 1)
    try:
        if ext == "msg":
            keys = [
                [_spec_key(parser.parse_message_string("pkg", stem, s))] for s in (orig, new)
            ]
        elif ext == "srv":
            specs = [parser.parse_service_string("pkg", stem, s) for s in (orig, new)]
            keys = [[_spec_key(x.request), _spec_key(x.response)] for x in specs]
        elif ext == "action":
            specs = [parser.parse_action_string("pkg", stem, s) for s in (orig, new)]
            keys = [
                [_spec_key(x.goal), _spec_key(x.result), _spec_key(x.feedback)] for x in specs
            ]
        else:
            return None
    except Exception:
        return False
    return keys[0] == keys[1]


def _cpp_tokens(src):
    import subprocess

    out = subprocess.run(
        ["g++", "-fpreprocessed", "-dD", "-E", "-P", "-x", "c++", "-"],
        input=src,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return " ".join(out.split())


def verify_cpp(orig, new):
    try:
        return _cpp_tokens(orig) == _cpp_tokens(new)
    except Exception:
        return False


def verify_python(orig, new):
    try:
        dump_a, docs_a = _normalized_python(orig)
        dump_b, docs_b = _normalized_python(new)
    except SyntaxError:
        return False
    if dump_a != dump_b or len(docs_a) != len(docs_b):
        return False
    for a, b in zip(docs_a, docs_b):
        if b == a:
            continue
        if "\n" in a and b.strip() == first_line(a):
            continue
        return False
    return True


SKIP_TOP_DIRS = (
    "maps", "bags", "docs", "models", "assets", "references", "android", "ios",
    "linux", "macos", "windows", "web", ".vscode", ".claude", "source_file",
    "location", "ekf_config", "build", "install", "log",
)
EXT_KINDS = {
    ".py": "python",
    ".yaml": "yaml", ".yml": "yaml",
    ".xml": "xml", ".xacro": "xml", ".urdf": "xml",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".h": "cpp", ".ino": "cpp",
    ".dart": "dart",
    ".sh": "shell", ".bash": "shell",
    ".lua": "lua",
    ".msg": "interface", ".srv": "interface", ".action": "interface",
    ".in": "hash", ".example": "hash",
}


def classify(path):
    """경로를 보고 어떤 언어 규칙으로 지울지 정한다. None 이면 손대지 않는다."""
    import os

    top = path.split("/", 1)[0]
    if top in SKIP_TOP_DIRS:
        return None
    base = os.path.basename(path)
    if base == "CMakeLists.txt":
        return "hash"
    return EXT_KINDS.get(os.path.splitext(base)[1])


STRIPPERS = {
    "python": (strip_python, verify_python),
    "yaml": (strip_yaml, verify_yaml),
    "xml": (strip_xml, verify_xml),
    "cpp": (lambda s: strip_clike(s, "cpp"), verify_cpp),
    "dart": (lambda s: strip_clike(s, "dart"), None),
    "shell": (strip_shell, verify_shell),
    "lua": (strip_lua, None),
    "interface": (strip_hash_lines, "interface"),
    "hash": (strip_hash_lines, None),
}


def process_file(root, rel):
    """한 파일을 지우고 검증한다. changed / unchanged / skipped / failed / ignored 를 돌려준다."""
    import os

    kind = classify(rel)
    if kind is None:
        return "ignored"
    path = os.path.join(root, rel)
    with open(path, "rb") as fh:
        raw = fh.read()
    try:
        src = raw.decode("utf-8")
    except UnicodeDecodeError:
        return "skipped"
    strip, verify = STRIPPERS[kind]
    try:
        new = strip(src)
    except Exception:
        return "failed"
    if new == src:
        return "unchanged"
    if verify == "interface":
        ok = verify_interface(rel, src, new)
    elif verify is not None:
        ok = verify(src, new)
    else:
        ok = None
    if ok is False:
        return "failed"
    with open(path, "wb") as fh:
        fh.write(new.encode("utf-8"))
    return "changed"


def _git_files(root):
    import subprocess

    out = subprocess.run(
        ["git", "-C", root, "ls-files", "-z"], capture_output=True, check=True
    ).stdout
    return [p.decode("utf-8") for p in out.split(b"\0") if p]


def process_tree(root, files=None):
    report = {k: [] for k in ("changed", "unchanged", "skipped", "failed", "ignored", "unverified")}
    for rel in files if files is not None else _git_files(root):
        status = process_file(root, rel)
        report[status].append(rel)
        kind = classify(rel)
        if status == "changed" and STRIPPERS[kind][1] is None:
            report["unverified"].append(rel)
    return report


def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(description="dev 원고에서 주석을 걷어내 main 인쇄본을 만든다")
    ap.add_argument("--root", default=".", help="git 저장소 경로 (기본: 현재 위치)")
    ap.add_argument("files", nargs="*", help="비우면 git ls-files 전체")
    args = ap.parse_args(argv)
    report = process_tree(args.root, args.files or None)
    for key in ("changed", "unchanged", "ignored", "skipped", "failed", "unverified"):
        print(f"{key:10s} {len(report[key])}")
    for key in ("skipped", "failed", "unverified"):
        for rel in report[key]:
            print(f"  [{key}] {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
