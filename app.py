from flask import Flask, jsonify

app = Flask(__name__)

@app.get("/")
def home():
    return "Server works"

@app.post("/chat")
def chat():
    return jsonify({"status": "chat endpoint works"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
