#!/usr/bin/env python3
"""Test Ollama connectivity and model availability."""

import asyncio
import sys

from ollama import AsyncClient


async def test_ollama():
    """Test Ollama connection and available models."""
    print("Testing Ollama connectivity...")

    try:
        client = AsyncClient(host="http://odysseus:11434")

        # Test model availability
        models_response = await client.list()
        available_models = []
        for model in models_response.models:
            if hasattr(model, "name"):
                available_models.append(model.name)
            elif hasattr(model, "model"):
                available_models.append(model.model)
            else:
                available_models.append(str(model))

        print(f"Available models: {available_models}")

        # Pick a model to test with
        target_model = available_models[0] if available_models else "llama3.2"
        print(f"Testing chat with '{target_model}'...")

        response = await client.chat(
            model=target_model,
            messages=[{"role": "user", "content": "Hello! Say hi back."}],
            options={"temperature": 0.1, "num_predict": 10},
        )

        response_text = response.message.content.strip()
        print(f"Model response: '{response_text}'")

        if response_text:
            print("Ollama connectivity test passed!")
            return True
        else:
            print("Ollama responded but got empty response")
            return True

    except Exception as e:
        print(f"Ollama test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_ollama())
    sys.exit(0 if success else 1)
