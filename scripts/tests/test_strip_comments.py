import textwrap
import unittest

from scripts import strip_comments as sc


def d(s):
    return textwrap.dedent(s).lstrip("\n")


class PythonStrip(unittest.TestCase):
    def test_removes_full_line_and_inline_comments_but_keeps_hash_in_strings(self):
        src = d('''
            import os  # inline comment

            # full line comment
            x = "# not a comment"
            y = 1
            ''')
        self.assertEqual(sc.strip_python(src), d('''
            import os

            x = "# not a comment"
            y = 1
            '''))

    def test_keeps_shebang_coding_and_pragma_comments(self):
        src = d('''
            #!/usr/bin/env python3
            # -*- coding: utf-8 -*-
            import sys  # noqa: E402
            y = 1  # type: int
            z = 2  # pragma: no cover - 설치 여부
            w = 3  # 그냥 설명
            ''')
        self.assertEqual(sc.strip_python(src), d('''
            #!/usr/bin/env python3
            # -*- coding: utf-8 -*-
            import sys  # noqa: E402
            y = 1  # type: int
            z = 2  # pragma: no cover - 설치 여부
            w = 3
            '''))

    def test_docstrings_keep_only_first_line(self):
        src = d('''
            """Module doc.

            Long description.
            """


            class A:
                """
                Summary on second line.

                Details.
                """

                def f(self):
                    """Do a thing.

                    More detail here.
                    """
                    return 1

                def g(self):
                    """Already one line."""
                    return 2
            ''')
        self.assertEqual(sc.strip_python(src), d('''
            """Module doc."""


            class A:
                """Summary on second line."""

                def f(self):
                    """Do a thing."""
                    return 1

                def g(self):
                    """Already one line."""
                    return 2
            '''))

    def test_blank_lines_collapse_but_multiline_strings_are_untouched(self):
        src = d('''
            x = 1



            # comment block


            def f():
                a = 1

                # note

                b = 2
                s = """line

                    kept

                """
                return a, b, s
            ''')
        self.assertEqual(sc.strip_python(src), d('''
            x = 1


            def f():
                a = 1

                b = 2
                s = """line

                    kept

                """
                return a, b, s
            '''))

    def test_trailing_whitespace_removed_and_single_final_newline(self):
        src = "x = 1   \ny = 2\t\n\n\n"
        self.assertEqual(sc.strip_python(src), "x = 1\ny = 2\n")

    def test_comment_only_file_becomes_empty(self):
        self.assertEqual(sc.strip_python("# only a comment\n"), "")

    def test_docstring_first_line_ending_with_quote_uses_single_quotes(self):
        src = d('''
            def f():
                """Returns "x"

                more
                """
                return 1
            ''')
        self.assertEqual(sc.strip_python(src), d("""
            def f():
                '''Returns "x"'''
                return 1
            """))

    def test_verify_python_accepts_correct_output_and_rejects_changed_code(self):
        src = d('''
            def f(x):
                """Doc.

                Long.
                """
                return x + 1  # add
            ''')
        good = sc.strip_python(src)
        self.assertTrue(sc.verify_python(src, good))
        self.assertFalse(sc.verify_python(src, good.replace("x + 1", "x + 2")))
        self.assertFalse(sc.verify_python(src, good.replace('"""Doc."""', '"""Other."""')))


class YamlStrip(unittest.TestCase):
    SRC = d('''
        # 상단 설명
        amcl:
          ros__parameters:
            # alpha 설명
            alpha1: 0.2 # 회전 오차
            frame: "map # 아님"
            plain: a#b
            plugins: ["general_goal_checker"] # "precise_goal_checker"
            text: |
              # 블록 스칼라 안은 내용
              line2


            other: 'x # y'
        ''')
    EXPECTED = d('''
        amcl:
          ros__parameters:
            alpha1: 0.2
            frame: "map # 아님"
            plain: a#b
            plugins: ["general_goal_checker"]
            text: |
              # 블록 스칼라 안은 내용
              line2

            other: 'x # y'
        ''')

    def test_removes_comments_but_keeps_hash_inside_scalars(self):
        self.assertEqual(sc.strip_yaml(self.SRC), self.EXPECTED)

    def test_verify_yaml_compares_loaded_values(self):
        self.assertTrue(sc.verify_yaml(self.SRC, self.EXPECTED))
        self.assertFalse(sc.verify_yaml(self.SRC, self.EXPECTED.replace("0.2", "0.3")))


class XmlStrip(unittest.TestCase):
    SRC = d('''
        <?xml version="1.0"?>
        <!-- 파일 설명 -->
        <package format="3">
          <name>vica_safety</name> <!-- 인라인 -->
          <!--
            여러 줄
            설명
          -->

          <depend>rclpy</depend>
        </package>
        ''')
    EXPECTED = d('''
        <?xml version="1.0"?>
        <package format="3">
          <name>vica_safety</name>

          <depend>rclpy</depend>
        </package>
        ''')

    def test_removes_xml_comments_and_their_lines(self):
        self.assertEqual(sc.strip_xml(self.SRC), self.EXPECTED)

    def test_verify_xml_compares_trees_without_comments(self):
        self.assertTrue(sc.verify_xml(self.SRC, self.EXPECTED))
        self.assertFalse(sc.verify_xml(self.SRC, self.EXPECTED.replace("rclpy", "rclcpp")))


class ClikeStrip(unittest.TestCase):
    CPP = d('''
        #include <string>  // include comment
        /* block
           comment */
        int main() {
          const char* url = "http://x/y";  // trailing
          char c = '/'; char q = '"'; // chars
          std::string s = "a // not comment";
          std::string raw = R"x(a // b /* c */)x";
          /* inline */ int z = 1;
          int w = 1; /* mid */ int v = 2;
          return 0;
        }
        ''')
    CPP_EXPECTED = d('''
        #include <string>
        int main() {
          const char* url = "http://x/y";
          char c = '/'; char q = '"';
          std::string s = "a // not comment";
          std::string raw = R"x(a // b /* c */)x";
          int z = 1;
          int w = 1; int v = 2;
          return 0;
        }
        ''')

    def test_cpp_comments_removed_but_strings_chars_and_raw_strings_kept(self):
        self.assertEqual(sc.strip_clike(self.CPP, "cpp"), self.CPP_EXPECTED)

    def test_doc_comment_block_keeps_only_first_line(self):
        src = d('''
            /// Summary line
            /// more detail
            /// even more
            void f();

            /// Other summary
            void g();
            ''')
        self.assertEqual(sc.strip_clike(src, "cpp"), d('''
            /// Summary line
            void f();

            /// Other summary
            void g();
            '''))

    def test_dart_strings_interpolation_and_ignore_pragmas(self):
        src = d('''
            import 'a.dart'; // c

            /// Doc line 1.
            ///
            /// Doc line 3.
            class A {
              // plain

              final s = 'ws://127.0.0.1:9090';
              final t = """multi // line

              end""";
              final r = r'\\d+ // x';
              final i = "${x ? 'a' : "b // c"} tail"; // trailing
              // ignore: unused_local_variable
              int y = 1;
            }
            ''')
        self.assertEqual(sc.strip_clike(src, "dart"), d('''
            import 'a.dart';

            /// Doc line 1.
            class A {

              final s = 'ws://127.0.0.1:9090';
              final t = """multi // line

              end""";
              final r = r'\\d+ // x';
              final i = "${x ? 'a' : "b // c"} tail";
              // ignore: unused_local_variable
              int y = 1;
            }
            '''))

    def test_verify_cpp_uses_preprocessor_token_stream(self):
        good = sc.strip_clike(self.CPP, "cpp")
        self.assertTrue(sc.verify_cpp(self.CPP, good))
        self.assertFalse(sc.verify_cpp(self.CPP, good.replace("http://x/y", "http://x/z")))


class ShellStrip(unittest.TestCase):
    SRC = (
        "#!/usr/bin/env bash\n"
        "# 설명\n"
        "set -euo pipefail  # inline\n"
        "if [ $# -ge 3 ]; then  # args\n"
        '  echo "###"\n'
        "  echo '# not comment'\n"
        "  n=${#arr[@]}\n"
        "fi\n"
        "cat <<'EOF'\n"
        "# heredoc line stays\n"
        "EOF\n"
        "cat <<-TAG\n"
        "\t# tabbed heredoc stays\n"
        "\tTAG\n"
        'msg="multi\n'
        "# inside quotes stays\n"
        'end"\n'
        "\n"
        "\n"
        "# shellcheck disable=SC2034\n"
        "unused=1\n"
    )
    EXPECTED = (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [ $# -ge 3 ]; then\n"
        '  echo "###"\n'
        "  echo '# not comment'\n"
        "  n=${#arr[@]}\n"
        "fi\n"
        "cat <<'EOF'\n"
        "# heredoc line stays\n"
        "EOF\n"
        "cat <<-TAG\n"
        "\t# tabbed heredoc stays\n"
        "\tTAG\n"
        'msg="multi\n'
        "# inside quotes stays\n"
        'end"\n'
        "\n"
        "# shellcheck disable=SC2034\n"
        "unused=1\n"
    )

    def test_shell_comments_removed_but_heredocs_quotes_and_pragmas_kept(self):
        self.assertEqual(sc.strip_shell(self.SRC), self.EXPECTED)

    def test_verify_shell_uses_bash_syntax_check(self):
        self.assertTrue(sc.verify_shell(self.SRC, self.EXPECTED))
        self.assertFalse(sc.verify_shell(self.SRC, "if [ 1 ]; then\n"))


class HashLineStrip(unittest.TestCase):
    MSG = d('''
        # 상시 긴급어 감지 이벤트
        string keyword        # 매칭된 긴급어
        string source_text "a#b" # 기본값에 # 포함
        float64 detected_at
        ---
        # response
        bool ok
        ''')
    MSG_EXPECTED = d('''
        string keyword
        string source_text "a#b"
        float64 detected_at
        ---
        bool ok
        ''')

    def test_hash_to_end_of_line_outside_quotes_is_removed(self):
        self.assertEqual(sc.strip_hash_lines(self.MSG), self.MSG_EXPECTED)

    def test_verify_interface_compares_parsed_fields(self):
        try:
            import rosidl_adapter  # noqa: F401
        except ImportError:
            self.skipTest("rosidl_adapter 없음 (ROS 환경 미소싱)")
        src = "# 요청\nstring keyword # 긴급어\n---\nbool ok # 응답\n"
        good = "string keyword\n---\nbool ok\n"
        self.assertTrue(sc.verify_interface("Foo.srv", src, good))
        self.assertFalse(sc.verify_interface("Foo.srv", src, good.replace("bool ok", "bool okay")))


class LuaStrip(unittest.TestCase):
    def test_lua_line_and_block_comments_removed_but_strings_kept(self):
        src = d('''
            -- 설명
            include "map_builder.lua"
            options = {
              map_frame = "map", -- 프레임
              s = "a -- b",
              --[[ block
              comment ]]
              n = 1,
              --[==[ long ]==]
              m = 2,
              t = [[long -- string]],
            }
            return options
            ''')
        self.assertEqual(sc.strip_lua(src), d('''
            include "map_builder.lua"
            options = {
              map_frame = "map",
              s = "a -- b",
              n = 1,
              m = 2,
              t = [[long -- string]],
            }
            return options
            '''))


class Classify(unittest.TestCase):
    def test_extension_and_skip_rules(self):
        cases = {
            "src/pkg/node.py": "python",
            "launch/x.launch.py": "python",
            "config/nav2_params.yaml": "yaml",
            "pubspec.yaml": "yaml",
            "src/pkg/package.xml": "xml",
            "urdf/a.xacro": "xml",
            "src/x.cpp": "cpp",
            "firmware/b.ino": "cpp",
            "lib/c.dart": "dart",
            "scripts/d.sh": "shell",
            "config/e.lua": "lua",
            "msg/A.msg": "interface",
            "srv/B.srv": "interface",
            "src/pkg/CMakeLists.txt": "hash",
            "scripts/bringup/layout.terminator.in": "hash",
            ".env.example": "hash",
            "maps/x.yaml": None,
            "bags/run/metadata.yaml": None,
            "docs/x.yaml": None,
            "android/app/build.gradle.kts": None,
            "linux/runner/main.cc": None,
            "web/index.html": None,
            ".vscode/settings.json": None,
            "models/m.onnx": None,
            "launch/old.launch": None,
            "README.md": None,
            "setup.cfg": None,
            "requirements.txt": None,
            "workspace.repos": None,
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(sc.classify(path), expected)


class ProcessFile(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, data):
        import os

        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        mode = "wb" if isinstance(data, bytes) else "w"
        with open(path, mode) as fh:
            fh.write(data)
        return path

    def read(self, rel):
        import os

        with open(os.path.join(self.root, rel)) as fh:
            return fh.read()

    def test_python_file_is_rewritten_and_reported_changed(self):
        self.write("a.py", "x = 1  # c\n")
        self.assertEqual(sc.process_file(self.root, "a.py"), "changed")
        self.assertEqual(self.read("a.py"), "x = 1\n")

    def test_file_without_comments_is_unchanged(self):
        self.write("a.py", "x = 1\n")
        self.assertEqual(sc.process_file(self.root, "a.py"), "unchanged")

    def test_non_utf8_file_is_skipped_and_left_alone(self):
        self.write("a.yaml", b"key: \xc0\xc1 # c\n")
        self.assertEqual(sc.process_file(self.root, "a.yaml"), "skipped")
        with open(self.root + "/a.yaml", "rb") as fh:
            self.assertEqual(fh.read(), b"key: \xc0\xc1 # c\n")

    def test_failed_verification_leaves_file_untouched(self):
        src = "a: !custom 1 # c\n"
        self.write("a.yaml", src)
        self.assertEqual(sc.process_file(self.root, "a.yaml"), "failed")
        self.assertEqual(self.read("a.yaml"), src)

    def test_process_tree_counts_by_status(self):
        self.write("a.py", "x = 1  # c\n")
        self.write("b.py", "x = 1\n")
        self.write("maps/m.yaml", "a: 1 # keep\n")
        report = sc.process_tree(self.root, ["a.py", "b.py", "maps/m.yaml"])
        self.assertEqual(report["changed"], ["a.py"])
        self.assertEqual(report["unchanged"], ["b.py"])
        self.assertEqual(report["ignored"], ["maps/m.yaml"])
        self.assertEqual(self.read("maps/m.yaml"), "a: 1 # keep\n")


class PublishMain(unittest.TestCase):
    def setUp(self):
        import os
        import subprocess
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.repo)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.put("old.md", "old main only\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "main base")
        self.git("checkout", "-q", "-b", "dev")
        self.git("rm", "-q", "old.md")
        self.put("a.py", "# 설명\nx = 1  # c\n")
        self.put("workspace.repos", "repositories:\n  r:\n    version: dev\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "dev work")
        self.git("checkout", "-q", "main")
        self.script = os.path.join(os.path.dirname(__file__), "..", "publish_main.sh")
        self.subprocess = subprocess

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        import subprocess

        return subprocess.run(
            ["git", "-C", self.repo, *args], capture_output=True, text=True, check=True
        ).stdout.strip()

    def put(self, rel, data):
        import os

        with open(os.path.join(self.repo, rel), "w") as fh:
            fh.write(data)

    def run_script(self, *extra):
        return self.subprocess.run(
            ["bash", self.script, self.repo, "dev", *extra], capture_output=True, text=True
        )

    def test_snapshot_merge_creates_two_parent_commit_with_stripped_tree(self):
        result = self.run_script("--manifest")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        parents = self.git("log", "-1", "--format=%P").split()
        self.assertEqual(len(parents), 2)
        self.assertEqual(parents[1], self.git("rev-parse", "dev"))
        self.assertEqual(self.git("show", "main:a.py"), "x = 1")
        self.assertEqual(self.git("show", "main:workspace.repos"), "repositories:\n  r:\n    version: main")
        self.assertNotIn("old.md", self.git("ls-tree", "-r", "--name-only", "main"))
        self.assertEqual(self.git("show", "dev:a.py"), "# 설명\nx = 1  # c")

    def test_second_run_without_new_dev_commits_is_a_no_op(self):
        self.run_script()
        head = self.git("rev-parse", "main")
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.git("rev-parse", "main"), head)


if __name__ == "__main__":
    unittest.main()
