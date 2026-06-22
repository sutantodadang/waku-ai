import embeddings


def test_cosine_identical_is_one():
    assert abs(embeddings.cosine([1.0, 0.0], [1.0, 0.0]) - 1.0) < 1e-9


def test_cosine_orthogonal_is_zero():
    assert abs(embeddings.cosine([1.0, 0.0], [0.0, 1.0])) < 1e-9


def test_cosine_zero_vector_is_zero():
    assert embeddings.cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_embed_texts_uses_provider(monkeypatch):
    monkeypatch.setattr(embeddings, "_embed_openai", lambda texts: [[0.1, 0.2]] * len(texts))
    monkeypatch.setattr(embeddings.settings, "llm_provider", "openai")
    monkeypatch.setattr(type(embeddings.settings), "use_openai", property(lambda self: True))
    out = embeddings.embed_texts(["a", "b"])
    assert out == [[0.1, 0.2], [0.1, 0.2]]
