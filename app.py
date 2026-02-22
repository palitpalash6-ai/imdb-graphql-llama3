from flask import Flask, request, jsonify
from ariadne import QueryType, MutationType, make_executable_schema, load_schema_from_path, graphql_sync
from ariadne.constants import PLAYGROUND_HTML
from db import movies_col, actors_col

app = Flask(__name__)

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
