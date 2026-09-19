import requests
import json

url = "http://localhost:7474/db/neo4j/tx/commit"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Basic bmVvNGo6cGFzc3dvcmQ=" # Using a guess, but it failed last time. Wait, I can't use REST without auth.
}
