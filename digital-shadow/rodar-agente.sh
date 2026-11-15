#!/bin/sh
# Subagente headless que constrói o Digital Shadow a partir de TAREFA.md e ESPEC.md.
# O log completo (stream-json) fica em agente.log.jsonl; o terminal mostra só o texto do agente.
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"
claude -p "Leia TAREFA.md e ESPEC.md nesta pasta e execute a tarefa descrita em TAREFA.md." \
  --add-dir ../bdg2-fl \
  --permission-mode acceptEdits \
  --allowedTools "Read" "Write" "Edit" "Glob" "Grep" \
    "Bash(npm:*)" "Bash(npx:*)" "Bash(node:*)" "Bash(uv:*)" "Bash(nice:*)" \
    "Bash(mkdir:*)" "Bash(ls:*)" "Bash(cat:*)" "Bash(head:*)" "Bash(wc:*)" "Bash(du:*)" \
  --output-format stream-json --verbose \
  | tee agente.log.jsonl \
  | jq -r --unbuffered '
      if .type == "assistant" then
        (.message.content[]? | if .type == "text" then "\n" + .text
                               elif .type == "tool_use" then "  > " + .name + " " + ((.input.command // .input.file_path // "") | tostring | .[0:120])
                               else empty end)
      elif .type == "result" then "\n=== fim: " + (.subtype // "") + " ===\n" + (.result // "")
      else empty end'
