"""`runa.run_internal`: execution-time helpers for the turn loop `runa.runner.Runner` drives.

One turn: call the model, then either return its text (subject to output guardrails) or execute
whatever tools it called (subject to tool guardrails and `needs_approval`) and loop. A handoff is
just a tool call whose name matches a registered `Handoff`; calling it switches `current_agent` for
the rest of the run. Tracing spans (`runa.tracing.Span`/`Trace`) are emitted directly as the loop
runs; there is no separate SDK trace to adapt from, so this is the one and only tracer.

Nothing here is public API: `Runner`, `RunState`, `RunResult`/`RunResultStreaming`, `RunConfig`,
`Interruption`, and the stream-event types all live at the top level instead (`runa.runner`,
`runa.run_state`, `runa.result`, `runa.run_config`, `runa.stream_events`), so this package holds
only execution-time detail: `run_loop` (the turn loop itself), `guardrails`, `tool_execution`,
`streaming`, `agent_runner_helpers` (model/instruction/tool resolution), and `spans` (tracing span
helpers).
"""
