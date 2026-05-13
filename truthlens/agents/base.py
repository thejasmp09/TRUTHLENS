"""
Base agent class.
All sub-agents inherit from this and implement execute().
Uses Gemini as the LLM backbone.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import config
from truthlens.llm import call_gemini

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Standard result returned by every agent."""
    agent_name: str
    status: str  # "success" | "error" | "no_data"
    data: dict = field(default_factory=dict)
    summary: str = ""
    error: str = ""


class BaseAgent(ABC):
    """
    Base class for all agents.
    Each agent has a name, a role description, and an execute() method.
    """

    name: str = "base"
    role: str = "A TruthLens agent."

    def __init__(self):
        self.logger = logging.getLogger(f"truthlens.agent.{self.name}")

    def call_llm(self, prompt: str) -> str:
        """Make a single Gemini call with automatic retry on rate limits."""
        return call_gemini(prompt)

    @abstractmethod
    def execute(self, context: dict) -> AgentResult:
        """
        Run this agent's task.
        
        Args:
            context: Shared context dictionary with keys like:
                - content: original post text
                - claims: list of extracted claims
                - source_url: URL of the original post
                - platform: reddit/bluesky/news
                - author: author of the original post
        
        Returns:
            AgentResult with agent's findings.
        """
        ...

    def __repr__(self) -> str:
        return f"<Agent:{self.name}>"
