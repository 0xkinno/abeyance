# SDK surface

Every Hermes surface Abeyance names, where we call it, where it lives in Hermes (commit `3d4dd108`),
and whether it is exercised. "Live" here means exercised on the real Hermes loop in the campaign;
"designed" means written to the documented contract but not yet exercised on that surface.

| Surface | Our code | Hermes | Status |
|---|---|---|---|
| `pre_tool_call` (block, approve) | `abeyance/__init__.py:160`, `engine.py` `pre_tool_call` | `hermes_cli/plugins.py:1119`, `_resolve_block_from_details` `:1198` | live |
| `post_tool_call` | `__init__.py:161` | hooks doc | live |
| `transform_llm_output` | `__init__.py:162` | hooks doc, `agent/turn_context.py` | live (cron output replaced) |
| `pre_llm_call` (context, block) | `__init__.py:163` | `agent/turn_context.py:863` | live |
| `subagent_start` | `__init__.py:164` | `tools/delegate_tool.py:367` | live |
| `ctx.current_cron_execution` | `__init__.py:27` | `hermes_cli/plugins_context.py:218`, `cron/execution_identity.py` | live |
| `gateway.session_context.get_session_env` | `__init__.py:34` | `gateway/session_context.py:230` | live |
| `agent.runtime_cwd.resolve_agent_cwd` | `__init__.py:41` | `agent/runtime_cwd.py:107` | live |
| `plugins.plugin_storage.plugin_db` | `store.py:78` | `plugins/plugin_storage.py:36` | live |
| `ctx.register_command` | `__init__.py:165` | `plugins_context.py:456` | registration live; slash dispatch tested with a fake ctx |
| `ctx.ask_choice` | `__init__.py:125` | `plugins_context.py:425` | designed (needs a chat surface) |
| `ctx.register_cli_command` | `cli.py:57` | `plugins_context.py:442` | registration live; parser tested |
| `ctx.register_skill` | `__init__.py:171` | `plugins_content.py:32` | live |
| `ctx.register_automation_blueprint` | `__init__.py:172` | `plugins_content.py:69` | live (accepted at registration) |
| `ctx.emit` and `broadcast_plugin_event` | `__init__.py:53,59` | `plugins_context.py:798`, `hermes_cli/plugin_events.py:71` | emit tested; Desktop delivery designed |
| Dashboard backend `plugin_api.py` | `abeyance/dashboard/` | desktop SDK doc, "The Python side" | designed (imported by the host, not yet called over HTTP) |
| Desktop SDK: chip, page, nav, directive, `host.composer.submit`, `ctx.onEvent` | `abeyance/desktop/plugin.js` | `website/docs/developer-guide/desktop-plugin-sdk.md` | desktop surface check passes; not yet run in the Desktop app |
| Approval gate via `request_tool_approval` | reached through the `approve` directive | `tools/approval.py:1246` | live (callback received our card) |

Not used, so not claimed: middleware, `register_tool`, approval transports, `register_platform`, any
network, any credential, `ctx.dispatch_tool`.
