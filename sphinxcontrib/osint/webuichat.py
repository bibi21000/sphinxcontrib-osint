# -*- encoding: utf-8 -*-
"""
Conversational agents backed by open-webui chat completions
-------------------------------------------------------------

This is deliberately independent from the Sphinx `WebUI` plugin (which runs
at doc-build time): it's meant to be instantiated once by a long-running
process (typically a Flask app) and reused across requests.

Expected config (same shape whether it comes from a Sphinx conf.py or a
Flask app config)::

    osint_webui_chat_token = "..."
    osint_webui_chat_url = "..."
    osint_webui_chat_knowledge = {
        "pravda": {"id": "...", "exclude-cats": ["..."]},
        "gremlin": {"id": "...", "only-cats": ["..."]},
    }
    osint_webui_chat_prompts = {
        "medor": {"prompt": "...", "model": "llama3.1"},
        "Octopus": {"prompt": "...", "model": "llama3.1"},
    }

Usage::

    chat = WebuiChat(
        url=osint_webui_chat_url,
        token=osint_webui_chat_token,
        knowledge=osint_webui_chat_knowledge,
        prompts=osint_webui_chat_prompts,
    )
    status, answer = chat.ask("medor", "pravda", "What happened this week?")

"""
import logging

from .owebuilib import OwebuiAPI

logger = logging.getLogger(__name__)


class WebuiChatAgent:
    """A single named conversational agent: one system prompt + one model,
    talking through a shared `OwebuiAPI` client.
    """

    def __init__(self, name, prompt, model, client):
        self.name = name
        self.prompt = prompt
        self.model = model
        self.client = client

    def ask(self, question, knowledge_id=None, history=None):
        return self.client.chat(self.model, self.prompt, question,
            knowledgeid=knowledge_id, history=history)


class WebuiChat:
    """Registry of conversational agents (e.g. "medor" for search, "Octopus"
    for analysis) sharing one open-webui chat endpoint, plus the named
    knowledge collections they can be grounded on.

    `knowledge` and `prompts` use the exact same dict shapes as
    `osint_webui_chat_knowledge` / `osint_webui_chat_prompts` in conf.py, so
    they can be passed straight through without reshaping.
    """

    def __init__(self, url, token, knowledge=None, prompts=None, default_model=None, **client_kwargs):
        self.client = OwebuiAPI(apikey=token, url_base=url, **client_kwargs)
        self.knowledge = knowledge or {}
        self.default_model = default_model
        self.agents = {}
        for name, cfg in (prompts or {}).items():
            model = cfg.get('model') or default_model
            if model is None:
                raise ValueError(
                    f"Chat agent '{name}' has no model configured: set "
                    f"'model' in osint_webui_chat_prompts['{name}'], or pass "
                    f"default_model= to WebuiChat().")
            self.agents[name] = WebuiChatAgent(name, cfg['prompt'], model, self.client)

    def ask(self, agent, knowledge, question, history=None):
        """Ask `question` to `agent` (a key of `osint_webui_chat_prompts`),
        grounded on `knowledge` (a key of `osint_webui_chat_knowledge`, or
        None for an ungrounded chat).

        Returns `(True, answer_text)` on success, `(False, raw_response)`
        otherwise. Raises `KeyError` if `agent` or `knowledge` is unknown -
        this is a programming/config error (typically a typo'd route
        parameter), not a transient failure, so it's not folded into the
        (status, ...) tuple like network/API errors are.
        """
        if agent not in self.agents:
            raise KeyError(f"Unknown chat agent '{agent}', available: {list(self.agents)}")

        knowledge_id = None
        if knowledge is not None:
            if knowledge not in self.knowledge:
                raise KeyError(f"Unknown chat knowledge '{knowledge}', available: {list(self.knowledge)}")
            knowledge_id = self.knowledge[knowledge]['id']

        return self.agents[agent].ask(question, knowledge_id=knowledge_id, history=history)
