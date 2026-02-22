from flask import Flask, request, jsonify
from ariadne import QueryType, MutationType, make_executable_schema, load_schema_from_path, graphql_sync
from ariadne.explorer import ExplorerGraphiQL
from db import movies_col, actors_col

import requests
import re

app = Flask(__name__)

# GraphiQL Explorer UI for GET /graphql
explorer_html = ExplorerGraphiQL().html(None)

# Load schema
type_defs = load_schema_from_path("schema.graphql")

query = QueryType()
mutation = MutationType()


# -----------------------
# GraphQL: Queries
# -----------------------
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


# -----------------------
# GraphQL: Mutations (Actors)
# -----------------------
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


# -----------------------
# GraphQL: Mutations (Movies)
# -----------------------
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


# -----------------------
# GraphQL routes
# -----------------------
@app.get("/graphql")
def playground():
    return explorer_html, 200


@app.post("/graphql")
def graphql_server():
    data = request.get_json(force=True)
    success, result = graphql_sync(schema, data, context_value={"request": request}, debug=True)
    return jsonify(result), (200 if success else 400)


# -----------------------
# Helper: Clean LLM output -> ONE GraphQL operation
# -----------------------
def extract_first_graphql_operation(text: str) -> str:
    if not text:
        return ""

    # remove markdown code fences: ``` or ```graphql
    cleaned = re.sub(r"```[a-zA-Z]*", "", text)
    cleaned = cleaned.replace("```", "").strip()

    # find first query/mutation
    m = re.search(r"\b(query|mutation)\b", cleaned)
    if not m:
        # fallback: start at first '{'
        b = cleaned.find("{")
        return cleaned[b:].strip() if b != -1 else cleaned.strip()

    s = cleaned[m.start():]

    # keep only first balanced {...} block to avoid multiple operations
    first_brace = s.find("{")
    if first_brace == -1:
        return s.strip()

    depth = 0
    end = None
    for i in range(first_brace, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    return s[:end].strip() if end else s.strip()


# -----------------------
# Chat route: Natural language -> Ollama -> GraphQL -> Execute
# -----------------------
@app.post("/chat")
def chat():
    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Missing 'message'"}), 400

    # load schema for grounding
    with open("schema.graphql", "r", encoding="utf-8") as f:
        schema_text = f.read()

    system_prompt = f"""
You convert the user's request into EXACTLY ONE GraphQL operation for THIS API.

Hard rules:
- Output ONLY GraphQL. No markdown. No backticks. No explanations. No schema text.
- Output EXACTLY ONE operation (one query OR one mutation).
- Must start with 'query' or 'mutation'.
- Use ONLY operations defined in the schema.
- For lists, always include a selection set, e.g.:
  query {{ getAllMovies {{ id title year rating }} }}

Schema:
{schema_text}
""".strip()

    # Ask Ollama
    r = requests.post(
        "http://127.0.0.1:11434/api/chat",
        json={
            "model": "llama3.2:1b",   # change to "llama3" if you pulled that model
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
        },
        timeout=90,
    )
    r.raise_for_status()

    raw = (r.json().get("message", {}).get("content") or "").strip()
    generated = extract_first_graphql_operation(raw)

    # Execute generated GraphQL against our own endpoint
    resp = requests.post(
        "http://127.0.0.1:8080/graphql",
        json={"query": generated},
        timeout=30,
    )

    return jsonify({
        "raw_llm": raw,
        "generated_graphql": generated,
        "result": resp.json(),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
