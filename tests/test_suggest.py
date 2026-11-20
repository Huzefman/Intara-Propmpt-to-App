from __future__ import annotations

import pytest
from services.suggest import suggest_next
from agents.schemas import ClarifyOption, ClarifyQuestion, S1ClarifyOut


def test_suggest_calendar_when_dates_present():
    spec = {
        "model": {
            "entities": [
                {
                    "id": "task",
                    "label": "Task",
                    "fields": [
                        {"id": "title", "type": "text"},
                        {"id": "due_date", "type": "date"},
                    ],
                }
            ]
        },
        "ui": {
            "pages": [
                {
                    "id": "tasks",
                    "blocks": [{"id": "b1", "type": "data.table"}],
                }
            ]
        },
        "access": {"roles": [{"id": "owner"}]},
        "automations": [],
    }
    suggestions = suggest_next(spec)
    labels = [s["label"] for s in suggestions]
    assert "Visual calendar" in labels
    cal = next(s for s in suggestions if s["label"] == "Visual calendar")
    assert "calendar" in cal["prompt"]
    assert "detail" in cal


def test_suggest_kanban_when_status_present():
    spec = {
        "model": {
            "entities": [
                {
                    "id": "ticket",
                    "label": "Ticket",
                    "fields": [
                        {"id": "title", "type": "text"},
                        {"id": "status", "type": "enum"},
                    ],
                }
            ]
        },
        "ui": {
            "pages": [
                {
                    "id": "tickets",
                    "blocks": [{"id": "b1", "type": "data.table"}],
                }
            ]
        },
        "access": {"roles": [{"id": "owner"}]},
        "automations": [],
    }
    suggestions = suggest_next(spec)
    labels = [s["label"] for s in suggestions]
    assert "Kanban board" in labels
    kb = next(s for s in suggestions if s["label"] == "Kanban board")
    assert "kanban" in kb["prompt"].lower()


def test_suggest_collaboration_for_single_role():
    spec = {
        "model": {
            "entities": [
                {
                    "id": "note",
                    "label": "Note",
                    "fields": [{"id": "content", "type": "text"}],
                }
            ]
        },
        "ui": {
            "pages": [
                {
                    "id": "notes",
                    "blocks": [{"id": "b1", "type": "data.table"}],
                }
            ]
        },
        "access": {"roles": [{"id": "owner"}]},
        "automations": [],
    }
    suggestions = suggest_next(spec)
    labels = [s["label"] for s in suggestions]
    assert "Team collaboration" in labels


def test_suggest_v1_prd_compat():
    prd = {
        "appType": "crm",
        "tables": [
            {"name": "leads", "fields": [{"name": "name", "type": "text"}]},
            {"name": "deals", "fields": [{"name": "amount", "type": "integer"}]},
        ],
    }
    suggestions = suggest_next(prd)
    assert len(suggestions) <= 4
    for s in suggestions:
        assert "label" in s and "detail" in s and "prompt" in s


def test_s1_schema_with_options():
    opt1 = ClarifyOption(label="Personal", desc="Single user")
    opt2 = ClarifyOption(label="Team", desc="Multi-user")
    q = ClarifyQuestion(id="q1", text="Is this personal or team?", options=[opt1, opt2])
    out = S1ClarifyOut(questions=[q], assumptions=["Single branch"])
    dumped = out.model_dump()
    assert dumped["questions"][0]["options"][0]["label"] == "Personal"
    assert dumped["questions"][0]["options"][1]["desc"] == "Multi-user"
