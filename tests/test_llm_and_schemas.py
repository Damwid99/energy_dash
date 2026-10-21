"""Testy modułu src/common/llm.py oraz schematów Pydantic z src/schemas/news.py."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.common.llm import _extract_json, ask_structured
from src.schemas.news import Digest, DigestItem, SelectedArticle, Selection


class TestNewsSchemas:
    """Testy walidacji modeli Pydantic dla newsów."""

    def test_selected_article_valid(self):
        art = SelectedArticle(id=5, horizon="short")
        assert art.id == 5
        assert art.horizon == "short"

    def test_selected_article_invalid_horizon(self):
        with pytest.raises(ValidationError):
            SelectedArticle(id=1, horizon="medium")  # type: ignore[arg-type]

    def test_selection_valid(self):
        sel = Selection.model_validate(
            {"selected": [{"id": 1, "horizon": "short"}, {"id": 2, "horizon": "long"}]}
        )
        assert len(sel.selected) == 2
        assert sel.selected[1].horizon == "long"

    def test_digest_item_valid(self):
        item = DigestItem(
            horizon="short",
            commodity="power",
            impact="up",
            summary="Spadek generacji wiatrowej podnosi ceny na RDN.",
            source_ids=[1, 3],
        )
        assert item.commodity == "power"
        assert item.impact == "up"

    @pytest.mark.parametrize(
        "field,bad_val",
        [
            ("horizon", "invalid"),
            ("commodity", "coal"),
            ("impact", "skyrocket"),
        ],
    )
    def test_digest_item_invalid_literals(self, field: str, bad_val: str):
        payload = {
            "horizon": "short",
            "commodity": "gas",
            "impact": "down",
            "summary": "Opis.",
            "source_ids": [1],
            field: bad_val,
        }
        with pytest.raises(ValidationError):
            DigestItem.model_validate(payload)

    def test_digest_model_validate_json(self):
        raw = """
        {
            "items": [
                {
                    "horizon": "long",
                    "commodity": "co2",
                    "impact": "neutral",
                    "summary": "Stabilizacja notowań EUA.",
                    "source_ids": [10, 12]
                }
            ]
        }
        """
        digest = Digest.model_validate_json(raw)
        assert len(digest.items) == 1
        assert digest.items[0].commodity == "co2"


class TestLlmModule:
    """Testy ekstrakcji JSON-a i wywołań ask_structured."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ('{"selected": []}', '{"selected": []}'),
            (
                'Oto wynik:\n```json\n{"selected": [{"id": 1, "horizon": "short"}]}\n```',
                '{"selected": [{"id": 1, "horizon": "short"}]}',
            ),
            ("Brak klamer w odpowiedzi", "Brak klamer w odpowiedzi"),
        ],
    )
    def test_extract_json(self, raw: str, expected: str):
        assert _extract_json(raw) == expected

    def test_ask_structured_first_try_success(self):
        fake_resp = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='```json\n{"selected": [{"id": 7, "horizon": "long"}]}\n```'
                    )
                )
            ]
        )
        with patch("src.common.llm.litellm.completion", return_value=fake_resp) as mock_comp:
            res = ask_structured("System prompt", "User prompt", Selection, max_retries=1)
            assert isinstance(res, Selection)
            assert len(res.selected) == 1
            assert res.selected[0].id == 7
            assert mock_comp.call_count == 1

    def test_ask_structured_retries_on_validation_error_and_recovers(self):
        bad_resp = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"selected": "not_a_list"}'))]
        )
        good_resp = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"selected": [{"id": 2, "horizon": "short"}]}')
                )
            ]
        )
        with patch(
            "src.common.llm.litellm.completion", side_effect=[bad_resp, good_resp]
        ) as mock_comp:
            res = ask_structured("System prompt", "User prompt", Selection, max_retries=1)
            assert res.selected[0].id == 2
            assert mock_comp.call_count == 2

    def test_ask_structured_raises_runtime_error_after_exhausting_retries(self):
        bad_resp = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="niepoprawny json"))]
        )
        with patch("src.common.llm.litellm.completion", return_value=bad_resp) as mock_comp:
            with pytest.raises(RuntimeError, match="LLM nie zwrócił poprawnego JSON-a"):
                ask_structured("System prompt", "User prompt", Selection, max_retries=1)
            assert mock_comp.call_count == 2
