import json


def get_data_once(name):
    with open(f"data/{name}.json", "r") as f:
        data = json.load(f)
    return data


async def get_data(name):
    with open(f"data/{name}.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


async def update_data(name, list):
    with open(f"data/{name}.json", "w") as f:
        json.dump(list, f)
