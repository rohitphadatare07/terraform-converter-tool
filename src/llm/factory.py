"""
LLM Factory - Supports multiple LLM providers.
Users can plug in their own API keys and models.
"""
from typing import Optional
from langchain_core.language_models import BaseChatModel


def get_llm(
    provider: str,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: float = 0.0,
    **kwargs,
) -> BaseChatModel:
    """
    Factory function to create an LLM instance.

    Supported providers:
        - openai      : GPT-4o, GPT-4-turbo, etc.
        - anthropic   : Claude 3.5 Sonnet, Claude 3 Opus, etc.
        - google      : Gemini 1.5 Pro, Gemini 1.5 Flash, etc.
        - groq        : Llama3, Mixtral (fast inference)
        - ollama      : Local models (no API key needed)
        - azure       : Azure OpenAI deployments

    Args:
        provider    : LLM provider name (case-insensitive).
        model       : Model name/ID. Falls back to a sensible default.
        api_key     : API key. Can also be set via env vars.
        temperature : Sampling temperature (0 = deterministic).
        **kwargs    : Extra kwargs forwarded to the LLM constructor.

    Returns:
        A LangChain BaseChatModel instance ready to use.
    """
    provider = provider.lower().strip()

    # ------------------------------------------------------------------ #
    #  OpenAI                                                              #
    # ------------------------------------------------------------------ #
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model or "gpt-4o",
            api_key=api_key,
            temperature=temperature,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Anthropic                                                           #
    # ------------------------------------------------------------------ #
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model or "claude-3-5-sonnet-20241022",
            api_key=api_key,
            temperature=temperature,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Google (Gemini)                                                     #
    # ------------------------------------------------------------------ #
    elif provider in ("google", "gemini"):
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model or "gemini-1.5-pro",
            google_api_key=api_key,
            temperature=temperature,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Groq (ultra-fast inference)                                         #
    # ------------------------------------------------------------------ #
    elif provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(
            model=model or "llama3-70b-8192",
            api_key=api_key,
            temperature=temperature,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Ollama (local models)                                               #
    # ------------------------------------------------------------------ #
    elif provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError:
            from langchain_community.chat_models import ChatOllama  # type: ignore

        return ChatOllama(
            model=model or "codellama:13b",
            temperature=temperature,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Azure OpenAI                                                        #
    # ------------------------------------------------------------------ #
    elif provider == "azure":
        from langchain_openai import AzureChatOpenAI

        return AzureChatOpenAI(
            azure_deployment=model or "gpt-4o",
            api_key=api_key,
            temperature=temperature,
            **kwargs,
        )

    else:
        supported = ["openai", "anthropic", "google", "groq", "ollama", "azure"]
        raise ValueError(
            f"Unknown provider '{provider}'. Supported providers: {supported}"
        )


# Convenience aliases
PROVIDER_DEFAULTS = {
    "openai": "gpt-4o",
    "anthropic": "claude-3-5-sonnet-20241022",
    "google": "gemini-1.5-pro",
    "groq": "llama3-70b-8192",
    "ollama": "codellama:13b",
    "azure": "gpt-4o",
}

PROVIDER_ENV_VARS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "ollama": None,  # No API key needed
    "azure": "AZURE_OPENAI_API_KEY",
}