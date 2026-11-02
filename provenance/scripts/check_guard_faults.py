"""Offline regression checks; no API calls or task execution."""
from guard_formal_run import is_infrastructure_fault

cases = [
    ({"exception_type": "AgentTimeoutError",
      "exception_message": "Agent execution timed out after 2400.0 seconds",
      "exception_traceback": 'File "_base.py", line 401\n litellm.acompletion\nAgentTimeoutError'}, False),
    ({"exception_type": "ValueError", "exception_message": "Parsing failed",
      "exception_traceback": 'File "parser.py", line 429'}, False),
    ({"exception_type": "AuthenticationError", "exception_message": "Invalid key"}, True),
    ({"exception_type": "litellm.exceptions.RateLimitError", "exception_message": "limit"}, True),
    ({"exception_type": "APIError", "exception_message": "Error code: 429 usage_limit_exceeded"}, True),
    ({"exception_type": "APIConnectionError", "exception_message": "Connection error"}, True),
    ({"exception_type": "ValueError", "exception_message": "HTTP 503 Service Unavailable"}, True),
    ({"exception_type": "ContextWindowExceededError", "exception_message": "context length exceeded"}, False),
    ({"exception_type": "CancelledError", "exception_message": ""}, False),
    ({}, False),
]
for info, expected in cases:
    assert is_infrastructure_fault(info) == expected, info
print(f"PASS: {len(cases)} offline guard checks; zero model calls")
