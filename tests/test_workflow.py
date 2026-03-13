"""Tests for workflow (copy/move + transcribe). Run with pytest; optional without real Whisper run."""

from pathlib import Path

import pytest

from wildfire.models_info import VALID_MODEL_IDS, WHISPER_MODELS
from wildfire.workflow import run


def test_models_info_structure():
    assert len(WHISPER_MODELS) >= 6
    for m in WHISPER_MODELS:
        assert "id" in m and "label" in m
        assert m["id"] in VALID_MODEL_IDS


def test_workflow_requires_existing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        run(
            tmp_path / "nonexistent.mp3",
            tmp_path / "out",
            "test",
            "tiny",
            move_instead_of_copy=False,
        )
