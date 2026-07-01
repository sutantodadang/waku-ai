import embeddings


def test_cosine_identical_is_one():
    assert abs(embeddings.cosine([1.0, 0.0], [1.0, 0.0]) - 1.0) < 1e-9


def test_cosine_orthogonal_is_zero():
    assert abs(embeddings.cosine([1.0, 0.0], [0.0, 1.0])) < 1e-9


def test_cosine_zero_vector_is_zero():
    assert embeddings.cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_embed_texts_uses_hf(monkeypatch):
    monkeypatch.setattr(embeddings, "_embed_hf", lambda texts: [[0.1, 0.2]] * len(texts))
    out = embeddings.embed_texts(["a", "b"])
    assert out == [[0.1, 0.2], [0.1, 0.2]]


def test_embed_texts_raises_when_hf_down(monkeypatch):
    import pytest
    monkeypatch.setattr(embeddings, "_embed_hf", lambda texts: None)
    with pytest.raises(RuntimeError):
        embeddings.embed_texts(["a"])
