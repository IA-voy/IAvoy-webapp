import pytest

from freshcode.core.edits import EditFormatError, apply_edits, parse_search_replace, parse_whole_files

REPLY = """Aquí van los cambios:

src/app.py
```python
<<<<<<< SEARCH
def hello():
    return "hi"
=======
def hello():
    return "hola"
>>>>>>> REPLACE
```

src/new.py
<<<<<<< SEARCH
=======
X = 1
>>>>>>> REPLACE
"""


def test_parse_blocks():
    edits = parse_search_replace(REPLY)
    assert [e.path for e in edits] == ["src/app.py", "src/new.py"]
    assert edits[0].search == 'def hello():\n    return "hi"\n'
    assert edits[1].search == ""


def test_apply_exact_and_create(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/app.py").write_text('def hello():\n    return "hi"\n')
    result = apply_edits(tmp_path, parse_search_replace(REPLY))
    assert result.failed == []
    assert '"hola"' in (tmp_path / "src/app.py").read_text()
    assert (tmp_path / "src/new.py").read_text() == "X = 1\n"


def test_fuzzy_match_reindents(tmp_path):
    (tmp_path / "m.py").write_text("class A:\n    def f(self):\n        return 1\n")
    reply = "m.py\n<<<<<<< SEARCH\ndef f(self):\n    return 1\n=======\ndef f(self):\n    return 2\n>>>>>>> REPLACE\n"
    result = apply_edits(tmp_path, parse_search_replace(reply))
    assert result.failed == []
    assert (tmp_path / "m.py").read_text() == "class A:\n    def f(self):\n        return 2\n"


def test_ambiguous_and_missing_search_fail(tmp_path):
    (tmp_path / "m.py").write_text("x = 1\nx = 1\n")
    reply = "m.py\n<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n>>>>>>> REPLACE\nm.py\n<<<<<<< SEARCH\ny = 9\n=======\ny = 0\n>>>>>>> REPLACE\n"
    result = apply_edits(tmp_path, parse_search_replace(reply))
    assert result.applied == []
    assert "2 veces" in result.failed[0][1]
    assert "no coincide" in result.failed[1][1]
    assert "m.py" in result.feedback()


def test_path_outside_repo_is_rejected(tmp_path):
    reply = "../evil.py\n<<<<<<< SEARCH\n=======\nboom\n>>>>>>> REPLACE\n"
    result = apply_edits(tmp_path, parse_search_replace(reply))
    assert result.applied == [] and "fuera del repo" in result.failed[0][1]


def test_unterminated_block_raises():
    with pytest.raises(EditFormatError):
        parse_search_replace("a.py\n<<<<<<< SEARCH\nx\n")


def test_whole_file_format(tmp_path):
    edits = parse_whole_files("FILE: a.py\n```python\nprint(1)\n```\n")
    apply_edits(tmp_path, edits)
    assert (tmp_path / "a.py").read_text() == "print(1)\n"
