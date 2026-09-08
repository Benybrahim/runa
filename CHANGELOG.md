# Changelog

All notable changes to this project will be documented here.

## Unreleased

* Replaced the `openai-agents`/`openai` SDK dependency with Runa's own in-house agent runtime:
  own agent loop (`runa._runner`), model layer (OpenAI-compatible providers over plain HTTP via
  `httpx2`, Claude via the `anthropic` SDK directly), tool/guardrail/handoff/session primitives,
  MCP client, and tracing. OpenAI's models remain a supported backend; only OpenAI's code was
  removed. The OpenAI-only `websocket_session` streaming feature was dropped (no cross-provider
  equivalent); `output_type` now supports basic JSON-mode output rather than full schema-strict
  parsing.
* Initial development
