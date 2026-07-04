import json
import asyncio
from typing import List, Dict, Any, Optional
import httpx
from loguru import logger

from src.core.managers import ConfigManager, WorkspaceManager
from src.core.loader import load_modules
from src.core.options import as_option


class ThinkingPartnerEngine:
    """AI-powered investigative thinking partner to scan graphs and suggest pivots."""

    # Thread-safe class-level task registry: {workspace_name: {"is_generating": bool, "logs": list[str]}}
    active_tasks: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def log_activity(cls, workspace_name: str, message: str, is_generating: bool = True):
        """Append a timestamped log message to the workspace's AI session activity log."""
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        log_line = f"{timestamp} | {message}"
        
        if workspace_name not in cls.active_tasks:
            cls.active_tasks[workspace_name] = {"is_generating": is_generating, "logs": []}
            
        cls.active_tasks[workspace_name]["is_generating"] = is_generating
        cls.active_tasks[workspace_name]["logs"].append(log_line)
        
        # Limit to last 50 log lines to prevent memory bloating
        if len(cls.active_tasks[workspace_name]["logs"]) > 50:
            cls.active_tasks[workspace_name]["logs"].pop(0)

    def __init__(self, config_path: str = "~/.keen/config.db") -> None:
        self.config_path = config_path

    async def generate_suggestions(
        self,
        workspace_name: str,
        user_query: Optional[str] = None,
        selected_nodes: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Scan the current workspace graph and generate investigative suggestions using configured LLM."""
        # Initialize logging state
        self.log_activity(workspace_name, "[AI] Initializing Thinking Partner scan...", is_generating=True)
        if user_query:
            self.log_activity(workspace_name, f"[AI] Investigator Query: '{user_query}'")
        if selected_nodes:
            self.log_activity(workspace_name, f"[AI] Focused on {len(selected_nodes)} selected nodes.")
        config = ConfigManager(self.config_path)
        workspace = None
        try:
            # Check if thinking partner is enabled
            enabled = config.get_preference("llm_thinking_partner_enabled")
            if enabled != "true":
                logger.info("AI Thinking Partner is disabled in preferences.")
                self.log_activity(workspace_name, "[AI] Thinking Partner is disabled in preferences.", is_generating=False)
                return []

            provider = config.get_preference("llm_provider") or "openai"
            model = config.get_preference("llm_model") or "gpt-4o"
            base_url = config.get_preference("llm_base_url") or ""

            # Fetch API Key from the secure keys store using provider name as service
            api_key = ""
            if config.is_unlocked():
                api_key = config.get_api_key(provider.lower()) or ""

            self.log_activity(workspace_name, f"[AI] Loading workspace '{workspace_name}' database...")
            w = config.get_workspace(workspace_name)
            if not w:
                logger.error(f"Workspace '{workspace_name}' not found.")
                self.log_activity(workspace_name, f"[AI] Error: Workspace '{workspace_name}' not found.", is_generating=False)
                return []

            workspace = WorkspaceManager(w["path"], name=workspace_name)

            self.log_activity(workspace_name, "[AI] Loading graph structure (nodes & edges)...")
            # 1. Fetch Graph State
            nodes = []
            cursor = workspace.conn.cursor()
            cursor.execute("SELECT id, type, value, metadata FROM nodes")
            for row in cursor.fetchall():
                meta = {}
                if row["metadata"]:
                    try:
                        meta = json.loads(row["metadata"])
                    except Exception:
                        pass
                nodes.append(
                    {
                        "id": row["id"],
                        "type": row["type"],
                        "value": row["value"],
                        "metadata": meta,
                    }
                )

            edges = []
            cursor.execute(
                "SELECT id, source_id, target_id, relationship, metadata FROM edge"
            )
            for row in cursor.fetchall():
                meta = {}
                if row["metadata"]:
                    try:
                        meta = json.loads(row["metadata"])
                    except Exception:
                        pass
                edges.append(
                    {
                        "id": row["id"],
                        "source_id": row["source_id"],
                        "target_id": row["target_id"],
                        "relationship": row["relationship"],
                        "metadata": meta,
                    }
                )
            self.log_activity(workspace_name, f"[AI] Loaded {len(nodes)} nodes and {len(edges)} edges.")

            if not nodes:
                logger.info("No nodes in workspace. Skipping AI suggestion generation.")
                self.log_activity(workspace_name, "[AI] Workspace is empty. Skipping scan.", is_generating=False)
                return []

            self.log_activity(workspace_name, "[AI] Scanning system for available OSINT modules...")

            # 2. Load Available Modules to supply as tools/options to LLM
            modules = load_modules()
            modules_summary = []
            for key, cls in modules.items():
                # Avoid duplicate keys (load_modules registers short, category/name, and full path)
                if "/" in key and not key.startswith("src."):
                    metadata = getattr(cls, "metadata", {})
                    options = {}
                    for opt_key, opt_val in metadata.get("options", {}).items():
                        opt = as_option(opt_val)
                        options[opt_key] = {
                            "default": opt.default,
                            "required": opt.required,
                            "description": opt.description,
                        }
                    modules_summary.append(
                        {
                            "module_id": key,
                            "name": metadata.get("name", key),
                            "description": metadata.get("description", ""),
                            "options_schema": options,
                        }
                    )

            self.log_activity(workspace_name, f"[AI] Context compiled. {len(modules_summary)} modules available.")

            # 3. Fetch past feedback to allow reinforcement learning in prompts
            cursor.execute(
                "SELECT suggestion_text, status, feedback FROM ai_suggestions WHERE status IN ('accepted', 'rejected') ORDER BY created_at DESC LIMIT 10"
            )
            feedback_history = [dict(row) for row in cursor.fetchall()]

            # 4. Formulate System & User Prompts
            system_prompt = (
                "You are an expert OSINT investigator and proactive Thinking Partner. Your job is to analyze the current investigation graph, "
                "identify matching patterns, correlations (e.g. matching usernames, emails, aliases across modules/sources), and formulate hypotheses.\n\n"
                "If the user has provided an 'investigator_instruction' in the payload, you MUST prioritize answering/addressing it in your case analysis and suggestions.\n"
                "If the user has provided 'selected_focus_nodes', prioritize generating pivot actions starting from or connecting to these specific nodes.\n\n"
                "You must perform two tasks and return the results in a single JSON object:\n"
                "1. Generate a high-level case analysis summary and synthesis (key findings, suspected patterns, overall hypotheses) formatted in clean Markdown.\n"
                "2. Suggest high-value next steps (pivots) for the investigator, using ONLY the available OSINT modules in the system.\n\n"
                "Available OSINT modules inside the system:\n"
                f"{json.dumps(modules_summary, indent=2)}\n\n"
                "The output must be a single JSON object conforming exactly to this schema:\n"
                "{\n"
                '  "analysis_summary": "Markdown-formatted text containing your high-level case synthesis, findings, and hypotheses.",\n'
                '  "suggestions": [\n'
                "    {\n"
                '      "suggestion_text": "Clear explanation of the pattern, matching correlation, or hypothesis, and why this pivot is recommended.",\n'
                '      "pivot_type": "run_module" or "manual_search" or "add_node",\n'
                '      "module_name": "The exact module_id of the suggested module (if pivot_type is run_module), or null",\n'
                '      "module_options": { "OptionKey": "Pre-filled option value based on graph data" } or null,\n'
                '      "context_nodes": ["List of node values or node IDs involved in this correlation or suggestion"]\n'
                "    }\n"
                "  ]\n"
                "}\n\n"
                "Return ONLY a raw JSON object. Do not wrap in markdown code blocks or add any conversational prologue/epilogue."
            )

            user_prompt: Dict[str, Any] = {
                "workspace": workspace_name,
                "current_graph": {"nodes": nodes, "edges": edges},
            }
            if user_query:
                user_prompt["investigator_instruction"] = user_query
            if selected_nodes:
                user_prompt["selected_focus_nodes"] = selected_nodes
            if feedback_history:
                user_prompt["user_feedback_history"] = feedback_history

            self.log_activity(workspace_name, f"[AI] Contacting LLM provider ({provider}) with model '{model}'...")
            # 5. Call LLM API
            suggestions_json = await self._call_llm(
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url,
                system_prompt=system_prompt,
                user_prompt=json.dumps(user_prompt, indent=2),
            )

            # 6. Parse and Save Suggestions
            parsed_suggestions = []
            if suggestions_json:
                self.log_activity(workspace_name, "[AI] Received response from LLM. Parsing suggestions...")
                # Strip markdown code block wrappers if the LLM ignored instructions
                cleaned_json = suggestions_json.strip()
                if cleaned_json.startswith("```"):
                    # Remove starting ```json or ```
                    first_newline = cleaned_json.find("\n")
                    if first_newline != -1:
                        cleaned_json = cleaned_json[first_newline:].strip()
                    if cleaned_json.endswith("```"):
                        cleaned_json = cleaned_json[:-3].strip()

                try:
                    parsed_data = json.loads(cleaned_json)
                    analysis_text = None
                    suggestions_list = []

                    if isinstance(parsed_data, dict):
                        analysis_text = parsed_data.get("analysis_summary")
                        suggestions_list = parsed_data.get("suggestions", [])
                    elif isinstance(parsed_data, list):
                        suggestions_list = parsed_data

                    # Save high-level thoughts/analysis if present
                    if analysis_text:
                        workspace.add_analysis(analysis_text)
                        self.log_activity(workspace_name, "[AI] Successfully saved high-level case analysis.")

                    for sug in suggestions_list:
                        sug_text = sug.get("suggestion_text")
                        if sug_text:
                            pivot_type = sug.get("pivot_type")
                            m_name = sug.get("module_name")
                            m_opts = sug.get("module_options", {})
                            ctx_nodes = sug.get("context_nodes", [])

                            # Save to workspace DB
                            workspace.add_suggestion(
                                suggestion_text=sug_text,
                                pivot_type=pivot_type,
                                module_name=m_name,
                                module_options=m_opts,
                                context_nodes=ctx_nodes,
                            )
                            parsed_suggestions.append(sug)
                    logger.info(
                        f"Successfully generated and stored {len(parsed_suggestions)} AI suggestions."
                    )
                    self.log_activity(workspace_name, f"[AI] Analysis complete. Generated and saved {len(parsed_suggestions)} suggestions.", is_generating=False)
                except json.JSONDecodeError as e:
                    logger.error(
                        f"Failed to parse AI response as JSON: {e}. Raw response: {suggestions_json}"
                    )
                    self.log_activity(workspace_name, f"[AI] Error: Failed to parse AI response as JSON.", is_generating=False)
            else:
                self.log_activity(workspace_name, "[AI] Error: Empty or failed response from LLM.", is_generating=False)

            return parsed_suggestions

        except Exception as e:
            logger.exception(f"Error generating AI suggestions: {e}")
            self.log_activity(workspace_name, f"[AI] Error: Exception occurred during scan: {str(e)}", is_generating=False)
            return []
        finally:
            if workspace:
                workspace.close()
            config.close()

    async def _call_llm(
        self,
        provider: str,
        model: str,
        api_key: str,
        base_url: str,
        system_prompt: str,
        user_prompt: str,
    ) -> Optional[str]:
        """Perform HTTP request to the selected LLM provider via its adapter."""
        from src.core.llm_providers import get_provider

        adapter = get_provider(provider)
        timeout = httpx.Timeout(45.0, connect=10.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                url, headers, payload = adapter.build_request(
                    model, api_key, base_url, system_prompt, user_prompt
                )
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                return adapter.parse_response(resp.json())
            except Exception as e:
                logger.error(f"HTTP error calling LLM provider '{provider}': {e}")
                return None
