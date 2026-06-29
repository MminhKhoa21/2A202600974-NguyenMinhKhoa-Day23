# Checklist tự chấm Day 08 LangGraph Agent — mục tiêu 100/100

> Tick checklist này trước khi nộp. Nếu một mục “Critical” chưa đạt, rủi ro mất điểm lớn hoặc fail hidden grading rất cao.

---

## 1. Critical rules

- [ ] Không hard-code theo `scenario_id` như `S01_simple`, `S02_tool`.
- [ ] Không hard-code exact query như `"How do I reset my password?"`.
- [ ] `classify_node` dùng LLM thật + structured output, không chỉ keyword heuristic.
- [ ] `answer_node` dùng LLM thật để sinh câu trả lời grounded.
- [ ] Mọi route đều kết thúc ở `finalize -> END`.
- [ ] Retry loop có giới hạn bằng `attempt < max_attempts`.
- [ ] Risky action phải đi qua approval/HITL trước khi tool/action chạy.
- [ ] Không commit `.env` hoặc API key.

---

## 2. Architecture & State Schema — 15/15

- [ ] `AgentState` là `TypedDict`, lean, serializable.
- [ ] Có đủ field gốc: `thread_id`, `scenario_id`, `query`, `route`, `risk_level`, `attempt`, `max_attempts`, `final_answer`.
- [ ] Có field bổ sung: `evaluation_result`, `pending_question`, `proposed_action`, `approval`.
- [ ] `messages`, `tool_results`, `errors`, `events` dùng reducer append-only.
- [ ] Field overwrite không dùng reducer append sai: `route`, `risk_level`, `attempt`, `final_answer`, `evaluation_result`, `approval`.
- [ ] `initial_state()` set default đầy đủ cho field mới.
- [ ] Node không mutate input state trực tiếp; chỉ return partial update dict.
- [ ] Event log đủ node name, event type, message, metadata cần thiết.

Tự chấm: `__/15`

---

## 3. Graph Construction & Wiring — 15/15

- [ ] `graph.py` import `StateGraph`, `START`, `END` bên trong `build_graph()`.
- [ ] Add đủ 11 node: `intake`, `classify`, `tool`, `evaluate`, `answer`, `clarify`, `risky_action`, `approval`, `retry`, `dead_letter`, `finalize`.
- [ ] Fixed edge: `START -> intake -> classify`.
- [ ] Conditional edge sau classify đúng mapping:
  - [ ] `simple -> answer`
  - [ ] `tool -> tool`
  - [ ] `missing_info -> clarify`
  - [ ] `risky -> risky_action`
  - [ ] `error -> retry`
- [ ] Tool path: `tool -> evaluate -> answer/retry`.
- [ ] Risky path: `risky_action -> approval -> tool/clarify`.
- [ ] Retry path: `retry -> tool/dead_letter`.
- [ ] Final path: `answer/clarify/dead_letter -> finalize -> END`.
- [ ] `graph.compile(checkpointer=checkpointer)` hoạt động.

Tự chấm: `__/15`

---

## 4. LLM Integration — 15/15

- [ ] `llm.py` hoặc runtime load được API key thật: `GEMINI_API_KEY`, `OPENAI_API_KEY`, hoặc `ANTHROPIC_API_KEY`.
- [ ] Cài đúng package provider, ví dụ `.[google]`, `.[openai]`, hoặc `.[anthropic]`.
- [ ] `classify_node` dùng `.with_structured_output(PydanticModel)` hoặc equivalent.
- [ ] Structured output giới hạn route vào: `simple`, `tool`, `missing_info`, `risky`, `error`.
- [ ] Prompt classification có priority rõ: risky > tool > missing_info > error > simple.
- [ ] `risk_level` set `high` cho risky.
- [ ] `answer_node` gọi LLM thật.
- [ ] `answer_node` grounded theo `query`, `tool_results`, `approval`, `errors`, không bịa ngoài context.
- [ ] `evaluate_node` dùng LLM-as-judge hoặc có fallback heuristic chắc chắn.
- [ ] Có fallback nếu LLM lỗi để graph không crash trong demo.

Tự chấm: `__/15`

---

## 5. Graph Behavior — 20/20

- [ ] `S01_simple` route ra `simple` và có final answer.
- [ ] `S02_tool` route ra `tool`, chạy tool, evaluate success, answer.
- [ ] `S03_missing` route ra `missing_info`, trả clarification question.
- [ ] `S04_risky` route ra `risky`, qua approval, rồi tool/evaluate/answer.
- [ ] `S05_error` route ra `error`, retry bounded, cuối cùng success hoặc dead-letter đúng logic.
- [ ] `S06_delete` route ra `risky`, có approval observed.
- [ ] `S07_dead_letter` route ra `error`, `max_attempts=1`, đi dead-letter không loop vô hạn.
- [ ] Custom risky hidden-like scenarios route đúng.
- [ ] Custom tool hidden-like scenarios route đúng.
- [ ] Custom vague/missing-info scenarios route đúng.
- [ ] Custom error/outage scenarios route đúng.
- [ ] Unknown route default không crash, fallback về answer.
- [ ] Tất cả route có `finalize` event.

Tự chấm: `__/20`

---

## 6. Persistence & Recovery — 10/10

- [ ] `build_checkpointer("memory")` vẫn hoạt động cho test/CI.
- [ ] `build_checkpointer("sqlite", database_url)` đã implement.
- [ ] SQLite dùng `SqliteSaver(conn=sqlite3.connect(...))`, không dùng API cũ nếu không tương thích.
- [ ] Connection SQLite có `check_same_thread=False`.
- [ ] Có WAL mode hoặc cấu hình ổn định.
- [ ] `graph.invoke(..., config={"configurable": {"thread_id": ...}})` hoạt động.
- [ ] Có bằng chứng checkpoint: file `.sqlite`, log state history, hoặc demo crash-resume.
- [ ] Report giải thích thread_id/state history/recovery evidence.
- [ ] Persistence không làm chậm hoặc fail `make run-scenarios`.

Tự chấm: `__/10`

---

## 7. Metrics & Tests — 15/15

- [ ] `pytest` pass.
- [ ] `pytest tests/test_routing.py` pass.
- [ ] `pytest tests/test_state.py` pass.
- [ ] `pytest tests/test_metrics.py` pass.
- [ ] `pytest tests/test_graph_smoke.py` pass khi có LLM key.
- [ ] `make run-scenarios` tạo `outputs/metrics.json`.
- [ ] `make grade-local` pass schema validation.
- [ ] `outputs/metrics.json` có `total_scenarios >= 7`.
- [ ] `success_rate == 1.0` với sample scenarios.
- [ ] `scenario_metrics` có actual route, retries, interrupts, errors meaningful.
- [ ] Approval-required scenarios có `approval_observed=true`.
- [ ] Error/dead-letter scenarios có retry count hợp lý.

Tự chấm: `__/15`

---

## 8. Report & Demo — 10/10

- [ ] `reports/lab_report.md` đã được generate hoặc viết hoàn chỉnh.
- [ ] Có thông tin student/team, repo/commit, date.
- [ ] Có architecture explanation: nodes, edges, state, reducers.
- [ ] Có metrics summary table.
- [ ] Có per-scenario result table.
- [ ] Có failure analysis ít nhất 2 mode:
  - [ ] Tool transient failure/retry/dead-letter.
  - [ ] Risky action without approval.
- [ ] Có persistence/recovery evidence.
- [ ] Có extension work rõ ràng.
- [ ] Có improvement plan nếu có thêm 1 ngày.
- [ ] Demo có thể giải thích ít nhất 1 route và 1 failure mode.

Tự chấm: `__/10`

---

## 9. Extension để chắc band 90–100

Chọn ít nhất 1, tốt nhất 2–3 mục:

- [ ] SQLite persistence thật.
- [ ] LLM-as-judge trong `evaluate_node`.
- [ ] Graph Mermaid diagram trong report.
- [ ] Real HITL bằng `interrupt()` khi `LANGGRAPH_INTERRUPT=true`.
- [ ] State history/time travel demo.
- [ ] Crash-resume demo.
- [ ] Parallel fan-out bằng `Send()` nếu muốn nâng cấp tool calls.
- [ ] Streamlit UI approval/reject nếu còn thời gian.

---

## 10. Command checklist cuối cùng

### Linux/macOS

```bash
pip install -e '.[dev,google,sqlite]'
pytest
ruff check src tests
mypy src
make run-scenarios
make grade-local
```

### Windows PowerShell

```powershell
py -m pip install -e ".[dev,google,sqlite]"
pytest
ruff check src tests
mypy src
python -m langgraph_agent_lab.cli run-scenarios --config configs/lab.yaml --output outputs/metrics.json
python -m langgraph_agent_lab.cli validate-metrics --metrics outputs/metrics.json
```

### Kết quả bắt buộc trước khi nộp

- [ ] `pytest`: PASS
- [ ] `ruff`: PASS
- [ ] `mypy`: PASS
- [ ] `make run-scenarios`: PASS
- [ ] `make grade-local`: PASS
- [ ] `outputs/metrics.json`: tồn tại và valid
- [ ] `reports/lab_report.md`: tồn tại và đủ nội dung
- [ ] Không có API key trong git diff

---

## 11. Bảng tự tính điểm

| Hạng mục | Điểm tối đa | Điểm tự chấm | Ghi chú |
|---|---:|---:|---|
| Architecture & state schema | 15 |  |  |
| Graph construction & wiring | 15 |  |  |
| LLM integration | 15 |  |  |
| Graph behavior | 20 |  |  |
| Persistence & recovery | 10 |  |  |
| Metrics & tests | 15 |  |  |
| Report & demo | 10 |  |  |
| **Tổng** | **100** |  |  |

Quy tắc quyết định:

- Nếu dưới 75: chưa nên nộp.
- Nếu 75–89: core chạy nhưng thiếu persistence/report/extension hoặc LLM chưa chắc.
- Nếu 90–100: graph production-quality, LLM thật, metrics/report đầy đủ, có extension và bằng chứng.
