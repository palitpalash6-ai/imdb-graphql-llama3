from flask import Flask, jsonify, render_template, request
from ariadne import (
    MutationType,
    QueryType,
    graphql_sync,
    load_schema_from_path,
    make_executable_schema,
)
from ariadne.explorer import ExplorerGraphiQL

from db import actors_col, movies_col
from llm import nl_to_graphql, ollama_status

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
    if actors_col.find_one({"id": str(id)}, {"_id": 1}):
        raise ValueError(f"Actor {id} already exists")

    doc = {"id": str(id), "name": name}
    actors_col.insert_one(doc)
    return doc


@mutation.field("updateActor")
def resolve_update_actor(*_, id, name):
    result = actors_col.update_one({"id": str(id)}, {"$set": {"name": name}})
    if result.matched_count == 0:
        raise ValueError(f"Actor {id} not found")

    return actors_col.find_one({"id": str(id)}, {"_id": 0})


@mutation.field("deleteActor")
def resolve_delete_actor(*_, id):
    result = actors_col.delete_one({"id": str(id)})
    if result.deleted_count == 0:
        raise ValueError(f"Actor {id} not found")

    return f"Actor {id} deleted"


@mutation.field("createMovie")
def resolve_create_movie(*_, id, input):
    if movies_col.find_one({"id": str(id)}, {"_id": 1}):
        raise ValueError(f"Movie {id} already exists")

    doc = {"id": str(id), **input}
    movies_col.insert_one(doc)
    return doc


@mutation.field("updateMovie")
def resolve_update_movie(*_, id, input):
    result = movies_col.update_one({"id": str(id)}, {"$set": input})
    if result.matched_count == 0:
        raise ValueError(f"Movie {id} not found")

    return movies_col.find_one({"id": str(id)}, {"_id": 0})


@mutation.field("deleteMovie")
def resolve_delete_movie(*_, id):
    result = movies_col.delete_one({"id": str(id)})
    if result.deleted_count == 0:
        raise ValueError(f"Movie {id} not found")

    return f"Movie {id} deleted"


schema = make_executable_schema(type_defs, [query, mutation])


# =========================
# Routes
# =========================


@app.route("/", methods=["GET"])
def home():
    return render_template("chatbot.html")


@app.route("/graphql", methods=["GET"])
def playground():
    return explorer_html, 200


@app.get("/ollama-status")
def get_ollama_status():
    status = ollama_status()
    code = 200 if status.get("ok") else 503
    return jsonify(status), code


@app.route("/graphql", methods=["POST"])
def graphql_server():
    data = request.get_json(silent=True)
    if not data or "query" not in data:
        return jsonify({"error": "Request JSON must contain a 'query' field"}), 400

    success, result = graphql_sync(schema, data, context_value={"request": request}, debug=True)
    status = 200 if success and "errors" not in result else 400
    return jsonify(result), status


@app.post("/chat")
def chat():
    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Missing 'message'"}), 400

    try:
        generated = nl_to_graphql(message).replace("selectionSet {", "")
    except Exception as e:
        status = ollama_status()
        return jsonify({"error": f"Ollama error: {str(e)}", "ollama": status}), 500

    _, result = graphql_sync(
        schema,
        {"query": generated},
        context_value={"request": request},
        debug=True,
    )
    return jsonify({"generated_graphql": generated, "result": result})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
