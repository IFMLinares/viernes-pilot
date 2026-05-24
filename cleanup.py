import requests

obs = requests.get("http://localhost:7437/observations", params={"project": "viernes"}).json()
for o in obs:
    if o.get("type") in ["conversacion", "manual"]:
        obs_id = o.get("id")
        title = o.get("title")
        r = requests.delete(f"http://localhost:7437/observations/{obs_id}")
        print(f"Borrando ID {obs_id} ({title}): {r.json().get('status')}")
