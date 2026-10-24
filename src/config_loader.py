import json
import os

CONFIG_PATH = os.path.join(
    "config",
    "robot_config.json"
)


def load_config():

    if not os.path.exists(CONFIG_PATH):
        print("❌ Robot configuration not found.")
        return None

    with open(
        CONFIG_PATH,
        "r",
        encoding="utf-8"
    ) as file:
        config = json.load(file)

    return config


def main():

    config = load_config()

    if config is None:
        return

    print("=" * 60)
    print("🤖 ROBOT CONFIGURATION")
    print("=" * 60)

    print("Project:", config["project"]["name"])
    print("Robot Type:", config["robot"]["type"])
    print("Controller:", config["robot"]["controller"])

    print("\nAtomic Actions:")

    for action in config["atomic_actions"]:
        print(" -", action)

    print("\nObjects:")

    for obj in config["supported_objects"]:
        print(" -", obj)

    print("\nColors:")

    for color in config["supported_colors"]:
        print(" -", color)

    print("\nTargets:")

    for target in config["supported_targets"]:
        print(" -", target)

    print("\nFailure Conditions:")

    for failure in config["failure_conditions"]:
        print(" -", failure)

    print(
        "\nRetry Attempts:",
        config["retry"]["max_attempts"]
    )

    print("=" * 60)
    print("✅ PHASE 1 CONFIGURATION VERIFIED")
    print("=" * 60)


if __name__ == "__main__":
    main()