"""Provider-neutral boundary for account-authenticated research agents.

Adapters own native session execution. The application owns data scope, durable
messages, typed tools and human confirmation. No API-key fallback is permitted.
"""
from typing import Protocol

class AnalystBackend(Protocol):
    def analyze(self, workspace, request, checkpoint) -> dict: ...


def backend(settings) -> AnalystBackend:
    from .codex import CodexCLI
    return CodexCLI(settings)

CAPABILITIES = {'provider':'codex','authentication':'subscription_login',
                'native_sessions':True,'vision':True,'skills':True,'chart_tools':True,'research_tools':True}
