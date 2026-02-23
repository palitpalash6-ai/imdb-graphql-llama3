# imdb-graphql-llama3

CS5600 Assignment 1 - GraphQL CRUD with MongoDB and Llama 3.

## Features

- GraphQL API for Movies and Actors with full CRUD mutations.
- MongoDB-backed storage (Atlas or local MongoDB).
- If MongoDB is unavailable at startup, the app falls back to an in-memory store for local/demo runs.
- `/chat` endpoint that converts plain English to GraphQL via Ollama and executes it.
- GraphiQL UI at `/graphql` for interactive testing.

## Setup

1. Create and activate a Python virtual environment.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file:

   ```env
   MONGODB_URI=mongodb://localhost:27017
   MONGODB_DB=imdb
   OLLAMA_URL=http://localhost:11434
   OLLAMA_MODEL=llama3.2:1b
   OLLAMA_TIMEOUT=120
   ```

4. Start Ollama and ensure the model is available:

   ```bash
   ollama serve
   ollama pull llama3.2:1b
   ```

5. Run the app:

   ```bash
   python app.py
   ```

## Endpoints

- `GET /` - Chatbot web UI.
- `GET /graphql` - GraphiQL playground.
- `POST /graphql` - Standard GraphQL execution endpoint.
- `POST /chat` - Natural language to GraphQL pipeline.
- `GET /ollama-status` - Check Ollama connectivity and model availability.

### Example `/chat` request

```json
{
  "message": "Show me all movies with their titles and ratings"
}
```

### Example GraphQL query

```graphql
query {
  getAllMovies {
    id
    title
    year
    rating
  }
}
```

## Quick test

Run the local test drill:

```bash
python -m unittest -v tests/test_app.py
```


## Ollama troubleshooting

1. Check Ollama health:

   ```bash
   curl http://127.0.0.1:8080/ollama-status
   ```

2. If not running, start it and pull the model:

   ```bash
   ollama serve
   ollama pull llama3.2:1b
   ```

3. Retry a chat request:

   ```bash
   curl -X POST http://127.0.0.1:8080/chat \
     -H "Content-Type: application/json" \
     -d '{"message":"show all actors"}'
   ```
