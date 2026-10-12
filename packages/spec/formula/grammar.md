# Formula language (v1)

Tiny expression language for computed fields, transition guards, automation
`when` clauses and block filters. LLMs write it; the parser validates it
(unknown field ⇒ lint error); the evaluator runs it. **Never `eval`.**

## Grammar

```
expr    := or_expr
or_expr := and_expr ("or" and_expr)*
and_expr:= not_expr ("and" not_expr)*
not_expr:= "not" not_expr | comparison
comparison := add (("==" | "!=" | "<" | "<=" | ">" | ">=") add)?
add     := mul (("+" | "-") mul)*
mul     := unary (("*" | "/" | "%") unary)*
unary   := "-" unary | primary
primary := number | string | "true" | "false" | "null"
         | path | call | "(" expr ")"
path    := ident ("." ident)*
call    := ident "(" [expr ("," expr)*] ")"
```

Precedence (low→high): `or`, `and`, `not`, comparison, `+ -`, `* / %`, unary `-`.
`and`/`or` return booleans. `if` is lazy (untaken branch never evaluates).

## Values

`null`, booleans, numbers (int/float, one IEEE-754 double at runtime),
strings (single/double quotes, `\\n \\t \\r \\\\ \\' \\"`), lists (only from
relation access), records (only from context — literals can't build them).

## Names

Bare `qty`, dotted `customer.name`. A dotted access on a **list** maps over
its elements: `parts.line_total` ⇒ `[2200, 300]`. Unknown names ⇒ error.
Reserved: `and or not true false null`.

## Functions

| fn | meaning |
|---|---|
| `if(c, a, b)` | lazy branch |
| `sum(list)` / `count(list)` / `min` / `max` / `avg` | aggregates; `sum([])=0`, `min/max/avg([])=null` |
| `len(x)` | string/list/record length |
| `str(x)` | `null→""`, bools→`true/false` |
| `int(x)` / `float(x)` | strict decimal conversion, else error |
| `now()` / `startOfMonth()` | ISO timestamps; evaluator takes fixed `now` for tests |

## Nulls & errors

`/` and `%` by zero ⇒ `null` (no throw). `null` propagates through
arithmetic as an error, compares equal only to `null`. `+` concats strings.
Anything else mismatched ⇒ `FormulaError`. Garbage text ⇒
`FormulaSyntaxError`. Both implementations share `formula-cases.json`
(118 cases); fuzz asserts only these two error types ever escape.

## Implementations

- `server/engine/formula.py` (Python — lint + server use)
- `formula.ts` (TypeScript — Studio/runtime use; erasable syntax, runs on node ≥22)
- Run: `node --test packages/spec/formula/formula.test.ts`
