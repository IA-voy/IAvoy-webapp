import shutil
import sys
from pathlib import Path

from freshcode.contracts import FreshFact
from freshcode.core.agent import AgentOptions, run_task
from freshcode.core.verify import trim_output
from freshcode.llm import ScriptedLLM

EXAMPLE = Path(__file__).parent.parent / "benchmark/tasks/example-slugify/repo"
TASK = "Implement slugify in textutils.py"
TEST_CMD = f'"{sys.executable}" -m pytest -q -p no:cacheprovider'

PLAN = '{"files": ["textutils.py"], "new_files": [], "libraries": [], "plan": "implement slugify"}'

WRONG = """textutils.py
<<<<<<< SEARCH
def slugify(text: str) -> str:
    raise NotImplementedError
=======
def slugify(text: str) -> str:
    return text.lower().replace(" ", "-")
>>>>>>> REPLACE
"""

RIGHT = """textutils.py
<<<<<<< SEARCH
def slugify(text: str) -> str:
    return text.lower().replace(" ", "-")
=======
def slugify(text: str) -> str:
    import re, unicodedata
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
>>>>>>> REPLACE
"""


def _copy_example(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(EXAMPLE, repo)
    return repo


def test_lean_run_retries_until_tests_pass(tmp_path):
    repo = _copy_example(tmp_path)
    llm = ScriptedLLM({"planner": [PLAN], "editor": [WRONG, RIGHT]})
    result = run_task(TASK, repo, llm, AgentOptions(config="lean", test_cmd=TEST_CMD))

    assert result.success and result.tests_ran
    assert result.retries == 1
    assert result.changed_files == ["textutils.py"]
    assert set(result.tokens_by_phase) == {"planner", "editor", "retry"}
    assert result.total_tokens == sum(result.tokens_by_phase.values())

    # El reintento manda el error recortado y el archivo actual, no el historial completo.
    role, retry_messages = llm.calls[-1]
    assert role == "editor" and len(retry_messages) == 2
    content = retry_messages[1]["content"]
    assert "test_slugify_accents_and_symbols" in content
    assert "def slugify" in content


def test_full_config_injects_fresh_facts(tmp_path, monkeypatch):
    repo = _copy_example(tmp_path)
    fact = FreshFact("use unicodedata.normalize", "fresh", 0.9, source_url="https://docs.python.org")
    monkeypatch.setattr("freshcode.stale_guard.check_claims", lambda plan, root, llm=None: [fact])
    right_from_start = RIGHT.replace('return text.lower().replace(" ", "-")', "raise NotImplementedError")
    llm = ScriptedLLM({"planner": [PLAN], "editor": [right_from_start]})

    result = run_task(TASK, repo, llm, AgentOptions(config="full", test_cmd=TEST_CMD))

    assert result.success and result.retries == 0
    assert result.facts == [fact]
    assert "FRESH FACTS" in llm.calls[-1][1][1]["content"]


def test_naive_sends_all_files_and_whole_file_edits(tmp_path):
    repo = _copy_example(tmp_path)
    whole = "FILE: textutils.py\n```python\n" + (EXAMPLE / "textutils.py").read_text().replace(
        "    raise NotImplementedError",
        '    import re, unicodedata\n'
        '    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()\n'
        '    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")',
    ) + "```\n"
    llm = ScriptedLLM({"editor": [whole]})

    result = run_task(TASK, repo, llm, AgentOptions(config="naive", test_cmd=TEST_CMD))

    assert result.success
    assert "test_textutils.py" in llm.calls[0][1][1]["content"]  # naive manda todo


def test_trim_output_keeps_signal():
    noisy = "\n".join(
        ["============ test session starts ============", "platform win32", "rootdir: x"]
        + [f"  File \"site-packages/lib{i}.py\", line {i}" for i in range(200)]
        + ["E   AssertionError: assert 'a b' == 'a-b'", "FAILED test_x.py::test_a - AssertionError", "1 failed, 2 passed"]
    )
    trimmed = trim_output(noisy, max_tokens=200)
    assert "AssertionError" in trimmed and "1 failed, 2 passed" in trimmed
    assert "site-packages" not in trimmed
