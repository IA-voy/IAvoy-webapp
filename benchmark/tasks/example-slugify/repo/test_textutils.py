from textutils import slugify, word_count


def test_word_count():
    assert word_count("hola mundo") == 2


def test_slugify_basic():
    assert slugify("Hola Mundo") == "hola-mundo"


def test_slugify_accents_and_symbols():
    assert slugify("  ¡Canción Ñandú! 2026 ") == "cancion-nandu-2026"
