import os
import re
import requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

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
    text = text.strip().replace("```graphql", "").replace("```", "").strip()
    m = re.search(r"(mutation|query)\s*[{(]", text)
    return text[m.start():].strip() if m else text

def nl_to_graphql(user_message: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    }
    r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=60)
    r.raise_for_status()
    content = r.json()["message"]["content"]
    gql = _extract_graphql(content)
    if not gql or len(gql) < 10:
        raise ValueError("LLM did not return valid GraphQL.")
    return gql
