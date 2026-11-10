from freshcode.core.repo_map import build_repo_map, js_symbols, python_symbols, render_repo_map
from freshcode.core.retrieval import keywords, load_context, rank_entries


def test_python_symbols():
    src = "class User(Base):\n    def name(self) -> str:\n        return ''\n\nasync def fetch(id: int):\n    pass\n"
    sigs = [(s.signature, s.depth) for s in python_symbols(src)]
    assert sigs == [("class User(Base)", 0), ("def name(self) -> str", 1), ("async def fetch(id: int)", 0)]


def test_js_symbols():
    src = (
        "export default async function GET(req, { params }) {\n"
        "export const useUser = (id: string) => {\n"
        "interface Props {\n"
        "class Store {\n"
    )
    assert [s.name for s in js_symbols(src)] == ["GET", "useUser", "Props", "Store"]


def test_map_ignores_node_modules_and_ranks(tmp_path):
    (tmp_path / "node_modules/x").mkdir(parents=True)
    (tmp_path / "node_modules/x/index.js").write_text("function nope() {}")
    (tmp_path / "users.py").write_text("def get_user(id):\n    pass\n")
    (tmp_path / "billing.py").write_text("def charge():\n    pass\n")

    entries = build_repo_map(tmp_path)
    assert [e.path for e in entries] == ["billing.py", "users.py"]
    ranked = rank_entries(entries, "fix getUser returning None")
    assert ranked[0].path == "users.py"
    assert "def get_user(id)" in render_repo_map(ranked)


def test_render_respects_budget(tmp_path):
    for i in range(50):
        (tmp_path / f"mod{i}.py").write_text("".join(f"def f{j}(a, b, c):\n    pass\n" for j in range(20)))
    text = render_repo_map(build_repo_map(tmp_path), max_tokens=300)
    assert len(text) // 4 <= 300
    assert "mod49.py" in text  # los que no caben quedan al menos como ruta


def test_keywords_split_identifiers():
    assert {"get", "user", "profile"} <= keywords("getUserProfile get_user")


def test_large_file_is_windowed(tmp_path):
    lines = [f"filler_{i} = {i}" for i in range(2000)]
    lines[1500] = "def checkout_total(cart):"
    (tmp_path / "big.py").write_text("\n".join(lines))
    ctx = load_context(tmp_path, ["big.py"], "fix checkout total", per_file_tokens=500)
    assert "def checkout_total(cart):" in ctx
    assert "omitidas" in ctx
    assert len(ctx) // 4 < 700
