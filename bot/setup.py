import json
import os

data = {
    "autorespond": {},
    "botconfig": {
        "system_instruction": None,
        "model": "gemini-3.5-flash-lite",
        "max_output_tokens": 1024,
        "thinking_level": None,
        "thinking_summaries": None,
        "tool_choice": None,
        "seed": None,
        "stop_sequences": None,
    },
    "botwhitelist": [],
    "brawlers": {},
    "channelwhitelist": [],
    "chathistory": {},
    "grammar": [],
    "guilds": [],
    "maps": [],
    "mute": [],
    "reminders": {},
    "soundboard": [],
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
