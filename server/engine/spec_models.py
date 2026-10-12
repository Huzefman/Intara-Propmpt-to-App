"""GENERATED from app-spec.schema.json by scripts/gen_spec_types.py — DO NOT EDIT."""
from __future__ import annotations

from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, Field


Id = Annotated[str, Field(pattern='^[a-z][a-z0-9_]*$')]


FieldType = Literal['text', 'longtext', 'int', 'decimal', 'money', 'bool', 'date', 'datetime', 'time', 'enum', 'multi_enum', 'ref', 'multi_ref', 'email', 'phone', 'url', 'file', 'image', 'rating', 'color', 'json']


class App(BaseModel):
    name: str
    tagline: str | None = None
    domain: str | None = None
    locale: str | None = None
    currency: str | None = None
    timezone: str | None = None


class Persona(BaseModel):
    id: Id
    name: str
    goals: list[str] = Field(default_factory=lambda: [])


class Requirement(BaseModel):
    id: str
    text: str
    priority: Literal['must', 'should', 'could'] = Field(default='should')
    persona: str | None = None


class EnumValue(BaseModel):
    value: str
    label: str
    color: str | None = None


class EnumDef(BaseModel):
    id: Id
    values: list[EnumValue]


class Computed(BaseModel):
    formula: str


class SpecField(BaseModel):
    id: Id
    type: FieldType
    required: bool | None = None
    unique: bool | None = None
    index: bool | None = None
    default: Any | None = None
    enum: str | None = None
    target: str | None = None
    onDelete: Literal['cascade', 'restrict', 'set_null'] | None = None
    relation_name: str | None = None
    computed: Computed | None = None


class Transition(BaseModel):
    id: Id
    from_: str = Field(alias="from")
    to: str
    label: str
    roles: list[str] = Field(default_factory=lambda: [])
    guard: str | None = None


class Lifecycle(BaseModel):
    field: str
    initial: str
    states: list[str] | None = None
    transitions: list[Transition] = Field(default_factory=lambda: [])


class Entity(BaseModel):
    id: Id
    label: str
    plural: str | None = None
    icon: str | None = None
    fields: list[SpecField]
    display: EntityDisplay | None = None
    lifecycle: Lifecycle | None = None


class Model(BaseModel):
    enums: list[EnumDef] = Field(default_factory=lambda: [])
    entities: list[Entity]


class Role(BaseModel):
    id: Id
    label: str | None = None


class AccessRule(BaseModel):
    entity: str
    role: str
    ops: list[Literal['read', 'create', 'update', 'delete']]
    where: str | None = None


class Access(BaseModel):
    roles: list[Role]
    rules: list[AccessRule]


class Theme(BaseModel):
    archetype: str | None = None
    palette: str | None = None
    density: Literal['compact', 'comfortable', 'spacious'] | None = None
    radius: str | None = None
    fonts: str | None = None


class NavItem(BaseModel):
    page: str
    label: str
    icon: str | None = None
    roles: list[str] = Field(default_factory=lambda: [])


class Block(BaseModel):
    id: Id
    type: str
    props: dict[str, Any] = Field(default_factory=lambda: {})


class Page(BaseModel):
    id: Id
    route: str
    title: str
    roles: list[str] = Field(default_factory=lambda: [])
    layout: str | None = None
    blocks: list[Block] = Field(default_factory=lambda: [])


class Ui(BaseModel):
    theme: Theme | None = None
    nav: list[NavItem] = Field(default_factory=lambda: [])
    pages: list[Page]


class AutoTrigger(BaseModel):
    type: Literal['record.created', 'record.updated', 'lifecycle.transition', 'schedule', 'manual_button']
    entity: str | None = None
    transition: str | None = None
    schedule: str | None = None


class AutoStep(BaseModel):
    action: Literal['set_field', 'create_record', 'send_email', 'notify', 'webhook', 'export_csv']
    when: str | None = None
    params: dict[str, Any] = Field(default_factory=lambda: {})


class Automation(BaseModel):
    id: Id
    trigger: AutoTrigger
    steps: list[AutoStep]


class Integration(BaseModel):
    type: Literal['email', 'file_storage', 'webhook']
    provider: str | None = None


class TraceEntry(BaseModel):
    requirement: str
    satisfied_by: list[str]


class EntityDisplay(BaseModel):
    title: str | None = None
    subtitle: str | None = None


class AppSpec(BaseModel):
    spec_version: str = Field(pattern='^\\d+\\.\\d+$')
    app: App
    personas: list[Persona] = Field(default_factory=lambda: [])
    requirements: list[Requirement] = Field(default_factory=lambda: [])
    assumptions: list[str] = Field(default_factory=lambda: [])
    model: Model
    access: Access
    ui: Ui
    automations: list[Automation] = Field(default_factory=lambda: [])
    seed: dict[str, list[dict[str, Any]]] = Field(default_factory=lambda: {})
    integrations: list[Integration] = Field(default_factory=lambda: [])
    trace: list[TraceEntry] = Field(default_factory=lambda: [])


__all__ = [
    "App",
    "Persona",
    "Requirement",
    "EnumValue",
    "EnumDef",
    "Computed",
    "SpecField",
    "Transition",
    "Lifecycle",
    "Entity",
    "Model",
    "Role",
    "AccessRule",
    "Access",
    "Theme",
    "NavItem",
    "Block",
    "Page",
    "Ui",
    "AutoTrigger",
    "AutoStep",
    "Automation",
    "Integration",
    "TraceEntry",
    "Id",
    "FieldType",
    "EntityDisplay",
    "AppSpec",
]
