from flask import Flask, request, jsonify
from ariadne import QueryType, MutationType, make_executable_schema, load_schema_from_path, graphql_sync
from ariadne.explorer import ExplorerGraphiQL
from db import movies_col, actors_col
import requests
import re

app = Flask(__name__)
explorer_html = ExplorerGraphiQL().html(None)

# =========================
# GraphQL Setup
# =========================
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

# =========================
# Helper: Clean LLM Output
# =========================
def clean_graphql(text: str) -> str:
    """
    Return ONLY the first GraphQL operation (query/mutation)
    and remove any explanation text after it.
    Also removes markdown fences.
    """
    if not text:
        return ""

    cleaned = text.replace("```graphql", "").replace("```", "").strip()

    # Find start of query or mutation
    m = re.search(r"\b(query|mutation)\b", cleaned)
    if m:
        cleaned = cleaned[m.start():].strip()
    else:
        # fallback: start at first {
        b = cleaned.find("{")
        if b == -1:
            return cleaned.strip()
        cleaned = cleaned[b:].strip()

    # Keep only the first balanced {...}
    first_brace = cleaned.find("{")
    if first_brace == -1:
        return cleaned.strip()

    depth = 0
    for i in range(first_brace, len(cleaned)):
        if cleaned[i] == "{":
            depth += 1
        elif cleaned[i] == "}":
            depth -= 1
            if depth == 0:
                return cleaned[: i + 1].strip()

    return cleaned.strip()

# =========================
# Routes
# =========================
@app.route("/graphql", methods=["GET"])
def playground():
    return explorer_html, 200

@app.route("/graphql", methods=["POST"])
def graphql_server():
    data = request.get_json()
    success, result = graphql_sync(schema, data, context_value={"request": request}, debug=True)
    status = 200 if success else 400
    return jsonify(result), status

@app.post("/chat")
def chat():
    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Missing 'message'"}), 400

    with open("schema.graphql", "r", encoding="utf-8") as f:
        schema_text = f.read()

    system_prompt = f"""
You translate the user's request into EXACTLY ONE GraphQL operation for THIS API.

ABSOLUTE RULES:
- Output ONLY the GraphQL operation text. No markdown. No backticks. No explanations.
- Must start with "query" or "mutation".
- NEVER invent field names. Use ONLY fields that appear in the schema below.
- For list queries, select fields directly (do NOT use "selectionSet").
- Use ONLY these root operations:
  Queries: getAllMovies, getMovieById, getAllActors, getActorById
  Mutations: createMovie, updateMovie, deleteMovie, createActor, updateActor, deleteActor

Valid examples:
query {{ getAllMovies {{ id title year rating }} }}
query {{ getAllActors {{ id name }} }}
query {{ getMovieById(id: "1") {{ id title year rating }} }}

Schema:
{schema_text}
""".strip()

    try:
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
            timeout=120,
        )
        r.raise_for_status()
        raw = (r.json().get("message", {}).get("content") or "").strip()

        generated = clean_graphql(raw)

        # Safety net: if the model still invents "selectionSet", strip it
        generated = generated.replace("selectionSet {", "")

    except Exception as e:
        return jsonify({"error": f"Ollama error: {str(e)}"}), 500

    try:
        resp = requests.post(
            "http://127.0.0.1:8080/graphql",
            json={"query": generated},
            timeout=60,
        )
        result = resp.json()
    except Exception as e:
        return jsonify({"raw_llm": raw, "generated_graphql": generated, "error": str(e)}), 500

    return jsonify({"raw_llm": raw, "generated_graphql": generated, "result": result})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
