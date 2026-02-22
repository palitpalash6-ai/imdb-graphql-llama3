from flask import Flask, request, jsonify
from ariadne import QueryType, MutationType, make_executable_schema, load_schema_from_path, graphql_sync
from ariadne.constants import PLAYGROUND_HTML
from db import movies_col, actors_col
from llm import nl_to_graphql
app = Flask(__name__)
import re

import asyncio
import httpx
from flask import request, jsonify
from llm import nl_to_graphql
type_defs = load_schema_from_path("schema.graphql")
query = QueryType()
mutation = MutationType()

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

@app.route("/graphql", methods=["GET"])
def playground():
    return PLAYGROUND_HTML, 200

@app.route("/graphql", methods=["POST"])
def graphql_server():
    data = request.get_json()
    success, result = graphql_sync(schema, data, context_value={"request": request}, debug=True)
    status = 200 if success else 400
    return jsonify(result), status

import requests  # add at top if missing

@app.post("/chat")
def chat():
    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Missing 'message'"}), 400

    # Load schema so the model generates the RIGHT operations
    with open("schema.graphql", "r", encoding="utf-8") as f:
        schema_text = f.read()

    system_prompt = f"""
You are a translator from English to GraphQL for THIS API.

ABSOLUTE RULES (must follow):
- Output ONLY the GraphQL operation. No markdown. No backticks. No explanations. No schema text.
- Output must start with "query" or "mutation".
- Use ONLY these operation names:
  Queries: getAllMovies, getMovieById, getAllActors, getActorById
  Mutations: createMovie, updateMovie, deleteMovie, createActor, updateActor, deleteActor
- getAllMovies must include a selection set, e.g.:
  query {{ getAllMovies {{ id title year rating }} }}
- getAllActors must include a selection set, e.g.:
  query {{ getAllActors {{ id name }} }}
- If the user asks to create something and does not give an id, invent a numeric string id like "9007".

Schema:
{schema_text}
""".strip()
    # Ask Ollama to produce GraphQL
    r = requests.post(
        "http://127.0.0.1:11434/api/chat",
        json={
            "model": "llama3.2:1b",
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
        },
        timeout=60,
    )
    r.raise_for_status()
    raw = (r.json().get("message", {}).get("content") or "").strip()
generated = extract_graphql(raw)
    # Execute the generated GraphQL against our own API
    resp = requests.post(
        "http://127.0.0.1:8080/graphql",
        json={"query": generated},
        timeout=30,
    )
    result = resp.json()

    return jsonify({"raw_llm": raw, "generated_graphql": generated, "result": result})
def extract_graphql(text: str) -> str:
    """
    Extract the first valid GraphQL operation from LLM output.
    Removes markdown fences and extra commentary.
    """
    if not text:
        return ""

    # Remove code fences
    cleaned = text.replace("```graphql", "").replace("```", "").strip()

    # Find first occurrence of a GraphQL operation
    m = re.search(r"\b(mutation|query)\b", cleaned)
    if not m:
        # Sometimes LLM returns just "{ ... }"
        m2 = re.search(r"\{", cleaned)
        return cleaned[m2.start():].strip() if m2 else cleaned

    return cleaned[m.start():].strip()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
