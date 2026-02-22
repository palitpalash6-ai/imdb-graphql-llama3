import requests
import re


def extract_first_graphql_operation(text: str) -> str:
    if not text:
        return ""

    # Remove markdown fences
    cleaned = re.sub(r"```[a-zA-Z]*", "", text)
    cleaned = cleaned.replace("```", "").strip()

    # Find first query/mutation
    m = re.search(r"\b(query|mutation)\b", cleaned)
    if not m:
        b = cleaned.find("{")
        return cleaned[b:].strip() if b != -1 else cleaned.strip()

    s = cleaned[m.start():]

    # Extract first balanced block
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


@app.post("/chat")
def chat():
    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()

    if not message:
        return jsonify({"error": "Missing 'message'"}), 400

    with open("schema.graphql", "r", encoding="utf-8") as f:
        schema_text = f.read()

    system_prompt = f"""
You convert the user's request into EXACTLY ONE GraphQL operation.

Rules:
- Output ONLY GraphQL.
- No markdown.
- No backticks.
- No explanations.
- Must start with query or mutation.
- Only use operations defined in the schema.

Schema:
{schema_text}
""".strip()

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
    generated = extract_first_graphql_operation(raw)

    resp = requests.post(
        "http://127.0.0.1:8080/graphql",
        json={"query": generated},
        timeout=30,
    )

    return jsonify({
        "raw_llm": raw,
        "generated_graphql": generated,
        "result": resp.json()
    })
