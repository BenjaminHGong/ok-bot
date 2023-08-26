import json

data = {
    "autorespond": {},
    "bank": {},
    "botwhitelist": [],
    "channelwhitelist":[],
    "grammar": [],
    "mute": [],
    "reminders": {}
}

for filename, content in data.items():
    with open(f"data/{filename}.json", "w") as file:
        json.dump(content, file, indent=4)