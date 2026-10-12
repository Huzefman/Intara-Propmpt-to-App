// GENERATED from app-spec.schema.json by scripts/gen_spec_types.py — DO NOT EDIT.

export type Id = string; // pattern: ^[a-z][a-z0-9_]*$

export type FieldType = "text" | "longtext" | "int" | "decimal" | "money" | "bool" | "date" | "datetime" | "time" | "enum" | "multi_enum" | "ref" | "multi_ref" | "email" | "phone" | "url" | "file" | "image" | "rating" | "color" | "json";

export interface App {
  name: string;
  tagline?: string;
  domain?: string;
  locale?: string;
  currency?: string;
  timezone?: string;
}

export interface Persona {
  id: Id;
  name: string;
  goals?: Array<string>;
}

export interface Requirement {
  id: string;
  text: string;
  priority?: "must" | "should" | "could";
  persona?: string;
}

export interface EnumValue {
  value: string;
  label: string;
  color?: string;
}

export interface EnumDef {
  id: Id;
  values: Array<EnumValue>;
}

export interface Computed {
  formula: string;
}

export interface SpecField {
  id: Id;
  type: FieldType;
  required?: boolean;
  unique?: boolean;
  index?: boolean;
  default?: unknown;
  enum?: string;
  target?: string;
  onDelete?: "cascade" | "restrict" | "set_null";
  relation_name?: string;
  computed?: Computed;
}

export interface Transition {
  id: Id;
  from: string;
  to: string;
  label: string;
  roles?: Array<string>;
  guard?: string;
}

export interface Lifecycle {
  field: string;
  initial: string;
  states?: Array<string>;
  transitions?: Array<Transition>;
}

export interface Entity {
  id: Id;
  label: string;
  plural?: string;
  icon?: string;
  fields: Array<SpecField>;
  display?: EntityDisplay;
  lifecycle?: Lifecycle;
}

export interface Model {
  enums?: Array<EnumDef>;
  entities: Array<Entity>;
}

export interface Role {
  id: Id;
  label?: string;
}

export interface AccessRule {
  entity: string;
  role: string;
  ops: Array<"read" | "create" | "update" | "delete">;
  where?: string;
}

export interface Access {
  roles: Array<Role>;
  rules: Array<AccessRule>;
}

export interface Theme {
  archetype?: string;
  palette?: string;
  density?: "compact" | "comfortable" | "spacious";
  radius?: string;
  fonts?: string;
}

export interface NavItem {
  page: string;
  label: string;
  icon?: string;
  roles?: Array<string>;
}

export interface Block {
  id: Id;
  type: string;
  props?: Record<string, unknown>;
}

export interface Page {
  id: Id;
  route: string;
  title: string;
  roles?: Array<string>;
  layout?: string;
  blocks?: Array<Block>;
}

export interface Ui {
  theme?: Theme;
  nav?: Array<NavItem>;
  pages: Array<Page>;
}

export interface AutoTrigger {
  type: "record.created" | "record.updated" | "lifecycle.transition" | "schedule" | "manual_button";
  entity?: string;
  transition?: string;
  schedule?: string;
}

export interface AutoStep {
  action: "set_field" | "create_record" | "send_email" | "notify" | "webhook" | "export_csv";
  when?: string;
  params?: Record<string, unknown>;
}

export interface Automation {
  id: Id;
  trigger: AutoTrigger;
  steps: Array<AutoStep>;
}

export interface Integration {
  type: "email" | "file_storage" | "webhook";
  provider?: string;
}

export interface TraceEntry {
  requirement: string;
  satisfied_by: Array<string>;
}

export interface EntityDisplay {
  title?: string;
  subtitle?: string;
}

export interface AppSpec {
  spec_version: string;
  app: App;
  personas?: Array<Persona>;
  requirements?: Array<Requirement>;
  assumptions?: Array<string>;
  model: Model;
  access: Access;
  ui: Ui;
  automations?: Array<Automation>;
  seed?: Record<string, Array<Record<string, unknown>>>;
  integrations?: Array<Integration>;
  trace?: Array<TraceEntry>;
}
