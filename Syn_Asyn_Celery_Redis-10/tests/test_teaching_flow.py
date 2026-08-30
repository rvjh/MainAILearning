from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.agent_pipeline import AgentPipeline
from app.errors import PermanentFailure, TransientFailure
from app.worker import RetryPolicy


class TeachingFlowTests(unittest.TestCase):
    def settings(self):
        return SimpleNamespace(
            allow_demo_faults=True,
            openai_api_key="",
            openai_model="deterministic",
        )

    def test_retry_policy_is_exponential_and_capped(self):
        policy = RetryPolicy(base_delay_seconds=1, max_delay_seconds=8)
        self.assertEqual([1, 2, 4, 8, 8], [policy.delay(n) for n in range(1, 6)])

    def test_controlled_transient_failure_occurs_only_for_requested_attempts(self):
        pipeline = AgentPipeline.__new__(AgentPipeline)
        with patch("app.agent_pipeline.get_settings", self.settings):
            with self.assertRaises(TransientFailure):
                pipeline._node_execute(
                    {
                        "attempts": 1,
                        "metadata": {"demo_transient_failures": "1"},
                        "thread_id": "thread-1",
                        "prompt": "Explain reliability",
                        "plan": {"plan": {"memory_context": []}},
                    }
                )
            result = pipeline._node_execute(
                {
                    "attempts": 2,
                    "metadata": {"demo_transient_failures": "1"},
                    "thread_id": "thread-1",
                    "prompt": "Explain reliability",
                    "plan": {"plan": {"memory_context": []}},
                }
            )
        self.assertEqual("deterministic", result["execute"]["model"])

    def test_controlled_permanent_failure_is_typed(self):
        pipeline = AgentPipeline.__new__(AgentPipeline)
        with patch("app.agent_pipeline.get_settings", self.settings):
            with self.assertRaises(PermanentFailure):
                pipeline._node_execute(
                    {
                        "attempts": 1,
                        "metadata": {"demo_permanent_failure": "true"},
                        "thread_id": "thread-1",
                        "prompt": "Explain reliability",
                        "plan": {"plan": {"memory_context": []}},
                    }
                )


if __name__ == "__main__":
    unittest.main()
