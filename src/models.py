"""Model registry: exact model ids served by one OpenAI-compatible endpoint.

The endpoint and key come from the environment (LLM_BASE_URL, LLM_API_KEY; see
.env.example), so anyone can point these model ids at their own provider.
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _model(model_id, **extra):
    return dict(model=model_id, base_url=os.getenv("LLM_BASE_URL"), key_env="LLM_API_KEY", **extra)


MODELS = {
    # small
    "bielik-11b": _model("bielik_11b"),
    # mid
    "qwen3.8-27b": _model("Qwen3.8-27B"),
    "mistral-small-24b": _model("Mistral-Small-3.2:24b"),
    # large
    "gpt-oss-120b": _model("gpt-oss_120b"),
    "deepseek-v4-flash": _model("DeepSeek-V4-Flash"),
}
