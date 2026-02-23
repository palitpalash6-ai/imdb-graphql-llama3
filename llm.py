import os
import re

import requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))

SYSTEM_PROMPT = """You convert user requests into ONE GraphQL operation only.
Output ONLY GraphQL (no backticks, no explanations).

Schema operations:
Queries:
- getAllMovies
- getMovieById(id: ID!)
- getAllActors
- getActorById(id: ID!)

Mutations:
- createMovie(id: ID!, input: MovieInput!)
- updateMovie(id: ID!, input: MovieInput!)
- deleteMovie(id: ID!)
- createActor(id: ID!, name: String!)
- updateActor(id: ID!, name: String!)
- deleteActor(id: ID!)

Rules:
- If user doesn't give an id for create, invent a numeric string like "9100".
- Prefer minimal fields in the selection set.
"""


def _extract_graphql(text: str) -> str:
    """Extract the first GraphQL operation from LLM output."""
    cleaned = text.strip().replace("```graphql", "").replace("```", "").strip()

    match = re.search(r"\b(query|mutation)\b", cleaned)
    if match:
        cleaned = cleaned[match.start() :].strip()
    else:
        brace_idx = cleaned.find("{")
        if brace_idx == -1:
            return cleaned
        cleaned = cleaned[brace_idx:].strip()

    first_brace = cleaned.find("{")
    if first_brace == -1:
        return cleaned

    depth = 0
    for idx in range(first_brace, len(cleaned)):
        if cleaned[idx] == "{":
            depth += 1
        elif cleaned[idx] == "}":
            depth -= 1
            if depth == 0:
                return cleaned[: idx + 1].strip()

    return cleaned


def ollama_status() -> dict:
    """Return Ollama connectivity and model availability status."""
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=10)
        response.raise_for_status()
        models = [m.get("name", "") for m in response.json().get("models", [])]
        return {
            "ok": True,
            "url": OLLAMA_URL,
            "model": OLLAMA_MODEL,
            "model_available": OLLAMA_MODEL in models,
            "available_models": models,
        }
    except requests.RequestException as exc:
        return {
            "ok": False,
            "url": OLLAMA_URL,
            "model": OLLAMA_MODEL,
            "error": str(exc),
            "hint": "Run 'ollama serve' and 'ollama pull llama3.2:1b'",
        }


def nl_to_graphql(user_message: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    }

    try:
        response = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=OLLAMA_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Cannot reach Ollama at {OLLAMA_URL}. Start it with 'ollama serve'. Details: {exc}"
        ) from exc

    content = response.json().get("message", {}).get("content", "")
    gql = _extract_graphql(content)
    if not gql or len(gql) < 10:
        raise ValueError("LLM did not return valid GraphQL.")
    return gql
