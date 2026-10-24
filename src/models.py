"""Every model is an OpenAI-compatible endpoint plus a model id."""

HF = "https://router.huggingface.co/v1"
OLLAMA = "http://localhost:11434/v1"

MODELS = {
    # Hugging Face Inference Providers (free monthly credits are tiny)
    "hf-gpt-oss-120b": dict(base_url=HF, key_env="HF_TOKEN", model="openai/gpt-oss-120b"),
    "hf-llama-3.3-70b": dict(base_url=HF, key_env="HF_TOKEN", model="meta-llama/Llama-3.3-70B-Instruct"),
    # Local, fully free (needs Ollama running; pick a model that supports tool calling)
    "ollama-qwen2.5-7b": dict(base_url=OLLAMA, key_env=None, model="qwen2.5:7b"),
        "gemini-flash": dict(base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                         key_env="GEMINI_API_KEY", model="gemini-3.5-flash-lite", delay=6),
}
