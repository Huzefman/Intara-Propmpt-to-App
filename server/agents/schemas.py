"""
Agent I/O schemas (Phase 7, P7.2): every agent declares typed input→output.
Spec slices reuse the generated models (engine/spec_models.py) — single
source of truth, no duplicated shapes.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from engine.spec_models import Access, Automation, Model, Ui


class S0IntakeOut(BaseModel):
    clean_wish: str = Field(min_length=4, max_length=2000)
    track: Literal["business", "freeform"] = "business"
    scope: str = "mvp"
    risk_flags: list[str] = Field(default_factory=list)
    language: str = "en"


class ClarifyQuestion(BaseModel):
    id: str
    text: str


class S1ClarifyOut(BaseModel):
    questions: list[ClarifyQuestion] = Field(default_factory=list, max_length=3)
    assumptions: list[str] = Field(default_factory=list)


class S2ModelOut(BaseModel):
    model: Model


class S3UiOut(BaseModel):
    ui: Ui


class S4LogicOut(BaseModel):
    access: Access
    automations: list[Automation] = Field(default_factory=list)


class Critique(BaseModel):
    requirement: str
    verdict: Literal["satisfied", "missing", "unclear"]
    note: str = ""


class S5CriticOut(BaseModel):
    trace: list[dict] = Field(default_factory=list)  # TraceEntry-shaped
    critiques: list[Critique] = Field(default_factory=list)
    unsatisfied: list[str] = Field(default_factory=list)  # must-ids lacking coverage


class S6SeedOut(BaseModel):
    seed: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


class IterationOut(BaseModel):
    patch: list[dict[str, Any]] = Field(min_length=1)
    summary: str = Field(min_length=4, max_length=500)
