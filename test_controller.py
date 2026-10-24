import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from robot_controller import RobotController


print("=" * 65)
print("🤖 PHASE 6 - ROBOT CONTROLLER TEST")
print("=" * 65)

robot = RobotController()

commands = [
    "DETECT",
    "MOVE",
    "GRAB",
    "MOVE",
    "RELEASE"
]

print("\n⚙️ Command Sequence:")
print(" → ".join(commands))

print("\n🚀 Starting Robot Execution...\n")

result = robot.execute_sequence(
    commands,
    object_name="red block",
    target="box"
)

print("\n" + "=" * 65)
print("📊 EXECUTION RESULT")
print("=" * 65)

for item in result["results"]:
    print(
        f"Step {item['step']}: "
        f"{item['command']} → "
        f"{item['status']} "
        f"(Attempts: {item['attempts']})"
    )

print("\nOverall Status:", result["overall_status"])
print("Robot Status:", result["robot_status"])

print("\n" + "=" * 65)
print("✅ PHASE 6 CONTROLLER TEST COMPLETED")
print("=" * 65)