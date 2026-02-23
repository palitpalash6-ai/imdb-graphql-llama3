import unittest
from unittest.mock import patch

import app
from db import InMemoryCollection


class AppRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()
        self._orig_actors = app.actors_col
        self._orig_movies = app.movies_col
        app.actors_col = InMemoryCollection()
        app.movies_col = InMemoryCollection()

    def tearDown(self):
        app.actors_col = self._orig_actors
        app.movies_col = self._orig_movies

    def post_graphql(self, query: str):
        return self.client.post("/graphql", json={"query": query})


    def test_home_page_renders_chatbot(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("IMDB GraphQL Chatbot", res.get_data(as_text=True))


    def test_ollama_status_endpoint(self):
        with patch("app.ollama_status", return_value={"ok": True, "model_available": True}):
            res = self.client.get("/ollama-status")

        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["ok"])

    def test_graphql_requires_query_field(self):
        res = self.client.post("/graphql", json={})
        self.assertEqual(res.status_code, 400)
        self.assertIn("query", res.get_json()["error"])

    def test_create_and_get_actor(self):
        create_res = self.post_graphql(
            'mutation { createActor(id:"10", name:"Neo") { id name } }'
        )
        self.assertEqual(create_res.status_code, 200)
        self.assertEqual(create_res.get_json()["data"]["createActor"]["name"], "Neo")

        get_res = self.post_graphql("query { getAllActors { id name } }")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(len(get_res.get_json()["data"]["getAllActors"]), 1)

    def test_duplicate_actor_is_rejected(self):
        self.post_graphql('mutation { createActor(id:"10", name:"Neo") { id name } }')
        dup_res = self.post_graphql(
            'mutation { createActor(id:"10", name:"Neo") { id name } }'
        )
        self.assertEqual(dup_res.status_code, 400)
        self.assertIn("already exists", dup_res.get_json()["errors"][0]["message"])


    def test_chat_returns_ollama_diagnostics_on_failure(self):
        with patch("app.nl_to_graphql", side_effect=RuntimeError("offline")), patch(
            "app.ollama_status", return_value={"ok": False, "hint": "start ollama"}
        ):
            res = self.client.post("/chat", json={"message": "show all actors"})

        self.assertEqual(res.status_code, 500)
        payload = res.get_json()
        self.assertIn("Ollama error", payload["error"])
        self.assertIn("ollama", payload)
        self.assertFalse(payload["ollama"]["ok"])

    def test_chat_executes_generated_graphql_in_process(self):
        gql = 'mutation { createActor(id:"22", name:"Trinity") { id name } }'
        with patch("app.nl_to_graphql", return_value=gql):
            res = self.client.post("/chat", json={"message": "create trinity actor"})

        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertEqual(payload["generated_graphql"], gql)
        self.assertEqual(payload["result"]["data"]["createActor"]["name"], "Trinity")


if __name__ == "__main__":
    unittest.main()
