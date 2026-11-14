def smell:
  . as $code
  | {"C901": "high-complexity",
   "PLR0913": "too-many-parameters",
   "PLR0915": "oversized-function",
   "F841": "unused-variable",
   "F401": "unused-import",
   "BLE001": "swallowed-exception",
   "invalid-syntax": "parse-error"}[$code] // $code;

group_by(.code | smell)
| map({smell: (.[0].code | smell),
       details: (if .[0].habit_hooks_project_rules and (.[0].code | smell) == .[0].code
                 then {diagnostic: true, tool: "ruff"} else {} end),
       issues: map({key: .filename,
                    details: {file: .filename,
                              line: .location.row,
                              column: .location.column,
                              message: .message,
                              source: ("ruff:" + .code)}})})
