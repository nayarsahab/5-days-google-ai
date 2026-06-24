.PHONY: install playground run-web generate-traces grade

install:
	agents-cli install

playground:
	uv run adk web expense_agent --host 127.0.0.1 --port 8081

run-web:
	uv run uvicorn expense_agent.web_service:app --host 127.0.0.1 --port 8080

generate-traces:
	uv run python tests/eval/generate_traces.py

grade:
	uv run python tests/eval/grade_traces.py

