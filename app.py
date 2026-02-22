from __future__ import annotations

import re
import requests
from flask import Flask, request, jsonify
from ariadne import QueryType, MutationType, make_executable_schema, load_schema_from_path, graphql_sync
from ariadne.constants import PLAYGROUND_HTML

from db import movies_col, actors_col

app = Flask(__name__)

# -----------------------------
# Helpers
# -----------------------------

def extract_first_graphql_operation(text: str) -> str:
    """
    Cleans LLM output and returns ONLY the first GraphQL operation (query/mutation).
    - Removes markdown fences/backticks
    - Skips any commentary before query/mutation
    - Trims to first balanced {...} block so we don't send multiple operations
    """
    if not text:
        return ""

    # Remove common markdown fences (``` or ```graphql)
    cleaned = text.replace("```graphql", "").replace("```", "").strip()

    # Find first 'query' or 'mutation'
    idx_q = cleaned.find("query")
    idx_m = cleaned.find("mutation")
    starts = [i for i in (idx_q, idx_m) if i != -1]
    if not starts:
        # fallback: start from first '{'
        b = cleaned.find("{")
        return cleaned[b:].strip() if b != -1 else cleaned.strip()

    start = min(starts)
    s = cleaned[start:].strip()

    # Cut out only the first balanced {...} operation
    brace_start = s.find("{")
    if brace_start == -1:
        return s

    depth = 0
    end = None
    for i in range(brace_start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    return s[:end].strip() if end else s.strip()


def build_system_prompt(schema_text: str) -> str:
    return f"""
You convert the user's request into EXACTLY ONE GraphQL operation for THIS API.

Hard rules (must follow):
- Output ONLY GraphQL. No markdown. No backticks. No explanations. No schema text.
- Output EXACTLY ONE operation (one query OR one mutation).
- Must start with 'query' or 'mutation'.
- Always include a selection set (fields), e.g. query {{ getAllMovies {{ id title }} }}.

Allowed operations:
Queries: getAllMovies, getMovieById, getAllActors, getActorById
Mutations: createMovie, updateMovie, deleteMovie, createActor, updateActor, deleteActor

If creating and user doesn't provide an id, invent a numeric string id like "9007".

Schema:
{schema_text}
""".strip()


# -----------------------------
# GraphQL Schema + Resolvers
# -----------------------------

type_defs = load_schema_from_path("schema.graphql")
query = QueryType()
mutation = MutationType()


# Queries
@query.field("getAllMovies")
def resolve_get_all_movies(*_):
    return list(movies_col.find({}, {"_id": 0}))


@query.field("getMovieById")
def resolve_get_movie_by_id(*_, id):
    return movies_col.find_one({"id": str(id)}, {"_id": 0})


@query.field("getAllActors")
def resolve_get_all_actors(*_):
    return list(actors_col.find({}, {"_id": 0}))


@query.field("getActorById")
def resolve_get_actor_by_id(*_, id):
    return actors_col.find_one({"id": str(id)}, {"_id": 0})


# Mutations - Actors
@mutation.field("createActor")
def resolve_create_actor(*_, id, name):
    doc = {"id": str(id), "name": name}
    actors_col.insert_one(doc)
    return doc


@mutation.field("updateActor")
def resolve_update_actor(*_, id, name):
    actors_col.update_one({"id": str(id)}, {"$set": {"name": name}})
    return actors_col.find_one({"id": str(id)}, {"_id": 0})


@mutation.field("deleteActor")
def resolve_delete_actor(*_, id):
    actors_col.delete_one({"id": str(id)})
    return f"Actor {id} deleted"


# Mutations - Movies
@mutation.field("createMovie")
def resolve_create_movie(*_, id, input):
    doc = {"id": str(id), **input}
    movies_col.insert_one(doc)
    return doc


@mutation.field("updateMovie")
def resolve_update_movie(*_, id, input):
    movies_col.update_one({"id": str(id)}, {"$set": input})
    return movies_col.find_one({"id": str(id)}, {"_id": 0})


@mutation.field("deleteMovie")
def resolve_delete_movie(*_, id):
    movies_col.delete_one({"id": str(id)})
    return f"Movie {id} deleted"


schema = make_executable_schema(type_defs, [query, mutation])


# -----------------------------
# Routes
# -----------------------------

@app.get("/")
def home():
    return "Server running. Go to /graphql or POST /chat", 200


@app.route("/graphql", methods=["GET"])
def playground():
    return PLAYGROUND_HTML, 200


@app.route("/graphql", methods=["POST"])
def graphql_server():
    data = request.get_json()
    success, result = graphql_sync(schema, data, context_value={"request": request}, debug=True)
    status = 200 if success else 400
    return jsonify(result), status


@app.post("/chat")
def chat():
    """
    POST /chat
    Body: { "message": "Show all movies" }
    Uses Ollama to convert NL -> GraphQL, then executes GraphQL and returns result.
    """
    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Missing 'message'"}), 400

    # Load schema for the LLM prompt
    with open("schema.graphql", "r", encoding="utf-8") as f:
        schema_text = f.read()

    system_prompt = build_system_prompt(schema_text)

    # Ask Ollama to produce GraphQL
    try:
        r = requests.post(
            "http://127.0.0.1:11434/api/chat",
            json={
                "model": "llama3.2:1b",   # change to "llama3" if you pulled it
                "stream": False,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ],
            },
            timeout=120,
        )
        r.raise_for_status()
        raw = (r.json().get("message", {}).get("content") or "").strip()
    except Exception as e:
        return jsonify({"error": f"Ollama call failed: {str(e)}"}), 500

    generated = extract_first_graphql_operation(raw)

    # Execute generated GraphQL against our own API
    try:
        resp = requests.post(
            "http://127.0.0.1:8080/graphql",
            json={"query": generated},
            timeout=60,
        )
        # GraphQL returns 200 even for errors sometimes; still parse JSON
        result = resp.json()
    except Exception as e:
        return jsonify({"raw_llm": raw, "generated_graphql": generated, "error": f"GraphQL exec failed: {str(e)}"}), 500

    return jsonify({"raw_llm": raw, "generated_graphql": generated, "result": result})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
