import json
import os

data = {
    "autorespond": {},
    "bank": {},
    "botwhitelist": [],
    "channelwhitelist": [],
    "grammar": [],
    "guilds": [],
    "mute": [],
    "reminders": {},
}

for filename, content in data.items():
    file_path = f"data/{filename}.json"

    if not os.path.exists(file_path):
        with open(file_path, "w") as file:
            json.dump(content, file, indent=4)
            print(f"Created {filename}.json")
    else:
        print(f"{filename}.json already exists")

if not os.path.exists("output.log"):
    with open("output.log", "w") as file:
        print("Created output.log")
else:
    print("output.log already exists")
