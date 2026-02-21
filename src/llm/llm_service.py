"""
FinSight AI — LLM Service
Supports local Ollama (default) and optional Gemini cloud fallback.
LLM is instructed to answer ONLY from provided context chunks with [Chunk X] citations.
"""
from typing import Any

from src.retrieval.retriever import RetrievedChunk

_SYSTEM_PROMPT = """You are FinSight AI, an expert financial document analyst.

RULES:
1. Answer ONLY from the context chunks provided below. Do NOT use any prior knowledge.
2. Cite your sources using the exact format [Chunk X] where X is the chunk number.
3. If the context does not contain enough information, respond with:
   "I don't have enough information in the provided documents to answer this question."
4. Be precise, professional, and concise. This is a financial compliance environment.
5. Never hallucinate figures, dates, or company names not present in the context."""


class LLMService:
    """Abstraction over local Ollama and optional Gemini cloud fallback."""

    def __init__(self, provider: str, **kwargs: Any) -> None:
        self.provider = provider.lower()

        if self.provider == "ollama":
            import ollama as _ollama
            self._model = kwargs.get("model", "llama3.1")
            self._ollama_client = _ollama.AsyncClient(
                host=kwargs.get("base_url", "http://localhost:11434")
            )

        elif self.provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=kwargs["api_key"])
            self._gemini_model = genai.GenerativeModel("gemini-2.5-flash")
            self._model = "gemini-2.5-flash"

        else:
            raise ValueError(f"Unsupported LLM provider: '{provider}'")

    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        """Generate a response from the LLM."""
        sys = system_prompt or _SYSTEM_PROMPT
        if self.provider == "ollama":
            return await self._call_ollama(prompt, sys)
        return await self._call_gemini(prompt, sys)

    async def _call_ollama(self, prompt: str, system_prompt: str) -> str:
        response = await self._ollama_client.chat(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": prompt},
            ],
            options={"temperature": 0.1, "num_predict": 1024},
        )
        return response.message.content.strip()

    async def _call_gemini(self, prompt: str, system_prompt: str) -> str:
        import asyncio
        full_prompt = f"{system_prompt}\n\n{prompt}"
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, self._gemini_model.generate_content, full_prompt
        )
        return response.text.strip()

    def build_rag_prompt(self, query: str, chunks: list[RetrievedChunk]) -> str:
        """Build prompt: context chunks with [Chunk X] markers + user question."""
        context_block = "\n\n---\n\n".join(
            f"[Chunk {i}] (Source: {c.source_file}, Relevance: {c.score:.2f})\n{c.text}"
            for i, c in enumerate(chunks, start=1)
        )
        return (
            f"CONTEXT DOCUMENTS:\n\n{context_block}\n\n---\n\n"
            f"USER QUESTION: {query}\n\n"
            f"Provide a thorough answer citing relevant [Chunk X] references."
        )

    @property
    def model_name(self) -> str:
        return self._model
