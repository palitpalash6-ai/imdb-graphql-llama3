import re
import requests
from flask import Flask, request, jsonify
from ariadne import QueryType, MutationType, make_executable_schema, load_schema_from_path, graphql_sync
from ariadne.constants import PLAYGROUND_HTML
from db import movies_col, actors_col

app = Flask(__name__)

# =========================
# Helper: Clean LLM Output
# =========================

def clean_graphql(text: str) -> str:
    if not text:
        return ""

    # Remove markdown fences
    text = text.replace("```graphql", "")
    text = text.replace("```", "")
    text = text.strip()

    # Start from first query or mutation
    idx_query = text.find("query")
    idx_mut = text.find("mutation")

    starts = [i for i in [idx_query, idx_mut] if i != -1]
    if not starts:
        brace = text.find("{")
        return text[brace:] if brace != -1 else text

    return text[min(starts):].strip()


# =========================
# GraphQL Setup
# =========================

type_defs = load_schema_from_path("schema.graphql")
query = QueryType()
mutation = MutationType()


# -------- Queries --------

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


# -------- Actor Mutations --------

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


# -------- Movie Mutations --------

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
# Routes
# =========================

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
    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()

    if not message:
        return jsonify({"error": "Missing 'message'"}), 400

    # Load schema for prompt grounding
    with open("schema.graphql", "r", encoding="utf-8") as f:
        schema_text = f.read()

    system_prompt = f"""
Convert the user request into EXACTLY ONE GraphQL operation.
Rules:
- Output ONLY GraphQL.
- No markdown.
- No backticks.
- Must start with query or mutation.
- Use only valid schema operations.

Schema:
{schema_text}
""".strip()

    # Call Ollama
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
    except Exception as e:
        return jsonify({"error": f"Ollama error: {str(e)}"}), 500

    generated = clean_graphql(raw)

    # Execute GraphQL
    try:
        resp = requests.post(
            "http://127.0.0.1:8080/graphql",
            json={"query": generated},
            timeout=60,
        )
        result = resp.json()
    except Exception as e:
        return jsonify({"raw_llm": raw, "generated_graphql": generated, "error": str(e)}), 500

    return jsonify({
        "raw_llm": raw,
        "generated_graphql": generated,
        "result": result
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
