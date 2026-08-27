import asyncio
import json


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path, data, indent=None):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent)


async def read_json_async(path):
    return await asyncio.to_thread(_read_json, path)


async def write_json_async(path, data, indent=None):
    await asyncio.to_thread(_write_json, path, data, indent)


def get_data_once(name):
    return _read_json(f"data/{name}.json")


async def get_data(name):
    return await read_json_async(f"data/{name}.json")


async def update_data(name, data):
    await write_json_async(f"data/{name}.json", data)


async def load_bot_config():
    return await read_json_async("data/botconfig.json")


async def save_bot_config(config):
    await write_json_async("data/botconfig.json", config, indent=4)
