"""Minimal supplier agent using the OpenAI Responses API."""

import os

from dotenv import load_dotenv
from openai import DefaultHttpxClient, OpenAI

from agent.tools import TOOL_SCHEMAS, TOOL_REGISTRY, execute_tool_call

load_dotenv()

http_client = DefaultHttpxClient(verify=False) if os.getenv("DISABLE_SSL_VERIFY") else None
client = OpenAI(http_client=http_client)
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4")

# TEMPLATE: Update accordingly
SYSTEM_PROMPT = (
    "You are a supplier accounts receivable assistant."
)


def run_agent_loop():
    conversation = [{"role": "developer", "content": SYSTEM_PROMPT}]

    print("Supplier AR Agent (type 'quit' to exit)")
    print("-" * 40)

    while True:
        user_input = input("\nYou: ").strip()
        if not user_input or user_input.lower() in ("quit", "exit"):
            break

        conversation.append({"role": "user", "content": user_input})

        while True:
            response = client.responses.create(
                model=MODEL,
                input=conversation,
                tools=TOOL_SCHEMAS,
            )

            has_tool_calls = False
            for item in response.output:
                if item.type == "function_call":
                    has_tool_calls = True
                    result = execute_tool_call(item, TOOL_REGISTRY)
                    conversation.append(item)
                    conversation.append(
                        {"type": "function_call_output", "call_id": item.call_id, "output": result}
                    )

            if not has_tool_calls:
                break

        print(f"\nAssistant: {response.output_text}")
        conversation.append({"role": "assistant", "content": response.output_text})


if __name__ == "__main__":
    run_agent_loop()
