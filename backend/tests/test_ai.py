import json

import pytest

from app.config import Settings
from app.schemas.event_log import SuggestedColumnMapping
from app.services.ai import data_linking
from app.services.ai.llm import LLMClient, LLMError, NullProvider, get_llm_client

COLUMNS = ["Case ID", "Action", "Completed At", "Agent", "Junk"]
ROWS = [
    {
        "Case ID": "1",
        "Action": "Open",
        "Completed At": "2023-01-01 08:00:00",
        "Agent": "alice",
        "Junk": "x",
    }
]


def test_ai_disabled_by_default():
    settings = Settings(ai_provider="none")
    assert get_llm_client(settings).enabled is False


def test_heuristic_mapping_matches_by_name():
    suggestion = data_linking.suggest_column_mapping(
        COLUMNS, ROWS, settings=Settings(ai_provider="none")
    )
    assert suggestion.source == "heuristic"
    assert suggestion.ai_enabled is False
    assert suggestion.mapping.case_id == "Case ID"
    assert suggestion.mapping.activity == "Action"
    assert suggestion.mapping.timestamp == "Completed At"
    assert suggestion.mapping.resource == "Agent"


def test_heuristic_sniffs_timestamp_by_value():
    cols = ["id", "step", "when_it_happened"]
    rows = [{"id": "1", "step": "Open", "when_it_happened": "2023-01-01 08:00:00"}]
    suggestion = data_linking.suggest_column_mapping(
        cols, rows, settings=Settings(ai_provider="none")
    )
    assert suggestion.mapping.timestamp == "when_it_happened"


class _FakeProvider:
    name = "openai"

    def __init__(self, payload: str):
        self._payload = payload

    def complete(self, *, system, user, json_mode):
        return self._payload


def test_structured_output_parses_valid_json():
    payload = json.dumps(
        {
            "mapping": {
                "case_id": "Case ID",
                "activity": "Action",
                "timestamp": "Completed At",
            },
            "confidence": 0.9,
            "reasoning": "obvious",
        }
    )
    client = LLMClient(_FakeProvider(payload), model="gpt-4o-mini")
    suggestion = data_linking.suggest_column_mapping(COLUMNS, ROWS, client=client)
    assert suggestion.source == "ai"
    assert suggestion.ai_enabled is True
    assert suggestion.mapping.activity == "Action"
    assert suggestion.confidence == 0.9


def test_ai_dropped_when_hallucinating_columns():
    payload = json.dumps(
        {
            "mapping": {"case_id": "DoesNotExist", "activity": "Action", "timestamp": None},
            "confidence": 0.5,
            "reasoning": "x",
        }
    )
    client = LLMClient(_FakeProvider(payload), model="gpt-4o-mini")
    suggestion = data_linking.suggest_column_mapping(COLUMNS, ROWS, client=client)
    # Hallucinated column is discarded; valid one kept.
    assert suggestion.mapping.case_id is None
    assert suggestion.mapping.activity == "Action"


def test_ai_falls_back_to_heuristic_on_bad_json():
    client = LLMClient(_FakeProvider("not json at all"), model="gpt-4o-mini")
    suggestion = data_linking.suggest_column_mapping(COLUMNS, ROWS, client=client)
    assert suggestion.source == "heuristic"
    assert "AI request failed" in suggestion.reasoning
    assert suggestion.mapping.case_id == "Case ID"


def test_structured_strips_code_fences():
    payload = "```json\n" + json.dumps(
        {"mapping": {"activity": "Action"}, "confidence": 0.3, "reasoning": ""}
    ) + "\n```"
    client = LLMClient(_FakeProvider(payload), model="gpt-4o-mini")
    suggestion = data_linking.suggest_column_mapping(COLUMNS, ROWS, client=client)
    assert suggestion.mapping.activity == "Action"


def test_null_provider_raises():
    with pytest.raises(LLMError):
        NullProvider().complete(system="", user="", json_mode=False)


def test_coerce_drops_unknown():
    mapping = SuggestedColumnMapping(case_id="real", activity="fake")
    coerced = data_linking._coerce_to_columns(mapping, ["real"])
    assert coerced.case_id == "real"
    assert coerced.activity is None
