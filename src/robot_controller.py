# ============================================================
# ROBOT CONTROLLER
# AI-POWERED RESTAURANT SERVICE ROBOT
# ============================================================


class RobotController:

    def __init__(self):

        # ----------------------------------------------------
        # Robot state
        # ----------------------------------------------------

        self.robot_status = "READY"
        self.current_location = "COUNTER"
        self.battery = 100

        self.customer_detected = False
        self.food_picked = False
        self.current_table = None

        self.current_order = None
        self.order_confirmed = False

        # Failure recovery demonstration
        self.failed_once = False
        self.demo_failure = True
        self.max_retries = 3


    # ========================================================
    # CUSTOMER DETECTION
    # ========================================================

    def detect_customer(self):

        print("👤 Detecting customer...")

        self.robot_status = "BUSY"
        self.customer_detected = True

        return {
            "status": "SUCCESS",
            "message": "Customer detected."
        }


    # ========================================================
    # GREET CUSTOMER
    # ========================================================

    def greet_customer(self):

        print("🤖 Robot: Welcome to our restaurant!")
        print("🤖 Robot: How may I help you today?")

        self.robot_status = "BUSY"

        return {
            "status": "SUCCESS",
            "message": "Customer greeted successfully."
        }


    # ========================================================
    # SHOW MENU
    # ========================================================

    def show_menu(self):

        print("📋 Showing restaurant menu...")

        print("""
        ================= MENU =================
        🍕 Pizza
        🍔 Burger
        🍝 Pasta
        🥤 Cold Drink
        💧 Water
        ☕ Coffee
        =========================================
        """)

        return {
            "status": "SUCCESS",
            "message": "Restaurant menu displayed."
        }


    # ========================================================
    # ASSIGN TABLE
    # ========================================================

    def assign_table(self, target="table 1"):

        print(f"🪑 Assigning customer to {target}...")

        self.current_table = target

        return {
            "status": "SUCCESS",
            "message": f"Customer assigned to {target}."
        }


    # ========================================================
    # MOVE TO CUSTOMER
    # ========================================================

    def move_to_customer(self):

        print("🚗 Moving robot to customer...")

        self.robot_status = "BUSY"

        return {
            "status": "SUCCESS",
            "message": "Robot moved to customer."
        }


    # ========================================================
    # GUIDE CUSTOMER
    # ========================================================

    def guide_customer(self, target="table 1"):

        print(f"🤖 Robot: Please follow me to {target}.")
        print(f"🚶 Guiding customer to {target}...")

        self.current_location = target
        self.current_table = target

        return {
            "status": "SUCCESS",
            "message": f"Customer guided to {target}."
        }


    # ========================================================
    # GET CURRENT LOCATION
    # ========================================================

    def get_current_location(self):

        print(
            f"📍 Robot current location: "
            f"{self.current_location}"
        )

        return {
            "status": "SUCCESS",
            "message":
                f"Current location: {self.current_location}"
        }


    # ========================================================
    # PLAN ROUTE
    # ========================================================

    def plan_route(self, target="table 1"):

        print(f"🗺️ Planning route to {target}...")

        return {
            "status": "SUCCESS",
            "message": f"Route planned to {target}."
        }


    # ========================================================
    # NAVIGATE TO TABLE
    # ========================================================

    def navigate_to_table(self, target="table 1"):

        print(f"🚗 Navigating robot to {target}...")

        self.robot_status = "BUSY"

        self.current_location = target
        self.current_table = target

        return {
            "status": "SUCCESS",
            "message": f"Robot navigated to {target}."
        }


    # ========================================================
    # CONFIRM ARRIVAL
    # ========================================================

    def confirm_arrival(self, target="table 1"):

        print(f"📍 Robot arrived at {target}.")

        return {
            "status": "SUCCESS",
            "message": f"Arrival at {target} confirmed."
        }


    # ========================================================
    # TAKE CUSTOMER ORDER
    # ========================================================

    def take_order(self, item="food"):

        print("📝 Taking customer order...")

        self.robot_status = "BUSY"
        self.current_order = item

        print(f"🤖 Robot: Your order is {item}.")

        return {
            "status": "SUCCESS",
            "message": f"Order taken successfully: {item}.",
            "order": item
        }


    # ========================================================
    # CONFIRM CUSTOMER ORDER
    # ========================================================

    def confirm_order(self, item="food"):

        print(f"🤖 Robot: Confirming order for {item}...")

        self.order_confirmed = True

        print(
            f"🤖 Robot: Your order for {item} "
            f"has been confirmed."
        )

        return {
            "status": "SUCCESS",
            "message": f"Order confirmed: {item}.",
            "order": item
        }


    # ========================================================
    # DETECT OBJECT
    # ========================================================

    def detect(self, object_name):

        print(f"🔍 Detecting {object_name}...")

        self.robot_status = "BUSY"

        return {
            "status": "SUCCESS",
            "message": f"Object detected: {object_name}"
        }


    # ========================================================
    # MOVE ROBOT
    # ========================================================

    def move(self, target):

        print(f"🚗 Moving robot to {target}...")

        self.robot_status = "BUSY"

        # ----------------------------------------------------
        # Demonstration failure
        # First MOVE fails once
        # Retry succeeds
        # ----------------------------------------------------

        if self.demo_failure and not self.failed_once:

            self.failed_once = True

            print("❌ Movement failed.")

            return {
                "status": "FAILED",
                "message":
                    "Movement failed. Obstacle detected."
            }

        print(f"✅ Robot moved to {target}")

        self.current_location = target

        return {
            "status": "SUCCESS",
            "message": f"Robot moved to {target}"
        }


    # ========================================================
    # GRAB OBJECT
    # ========================================================

    def grab(self, object_name):

        print(f"✋ Grabbing {object_name}...")

        self.robot_status = "BUSY"
        self.food_picked = True

        return {
            "status": "SUCCESS",
            "message":
                f"Successfully grabbed {object_name}"
        }


    # ========================================================
    # RELEASE OBJECT
    # ========================================================

    def release(self, target):

        print(f"📦 Releasing object at {target}...")

        self.robot_status = "BUSY"
        self.food_picked = False

        return {
            "status": "SUCCESS",
            "message":
                f"Object released at {target}"
        }


    # ========================================================
    # CONFIRM DELIVERY
    # ========================================================

    def confirm_delivery(self, target="table"):

        print(f"✅ Delivery confirmed at {target}.")
        print("🤖 Robot: Enjoy your meal!")

        return {
            "status": "SUCCESS",
            "message":
                f"Delivery confirmed at {target}."
        }


    # ========================================================
    # RETURN TO COUNTER
    # ========================================================

    def return_to_counter(self):

        print("🔙 Robot returning to counter...")

        self.robot_status = "BUSY"

        self.current_location = "COUNTER"
        self.current_table = None

        return {
            "status": "SUCCESS",
            "message": "Robot returned to counter."
        }


    # ========================================================
    # STOP ROBOT
    # ========================================================

    def stop(self):

        self.robot_status = "STOPPED"

        print("🛑 Robot stopped.")

        return {
            "status": "SUCCESS",
            "message": "Robot stopped."
        }


    # ========================================================
    # EXECUTE SINGLE COMMAND
    # ========================================================

    def execute_command(
        self,
        command,
        object_name="object",
        target="target"
    ):

        command = command.upper()

        # ====================================================
        # CUSTOMER SERVICE
        # ====================================================

        if command == "DETECT_CUSTOMER":

            return self.detect_customer()


        elif command == "GREET":

            return self.greet_customer()


        elif command == "SHOW_MENU":

            return self.show_menu()


        elif command == "ASSIGN_TABLE":

            return self.assign_table(target)


        elif command == "MOVE_TO_CUSTOMER":

            return self.move_to_customer()


        elif command == "GUIDE":

            return self.guide_customer(target)


        # ====================================================
        # NAVIGATION
        # ====================================================

        elif command == "GET_LOCATION":

            return self.get_current_location()


        elif command == "PLAN_ROUTE":

            return self.plan_route(target)


        elif command == "NAVIGATE":

            return self.navigate_to_table(target)


        elif command == "CONFIRM_ARRIVAL":

            return self.confirm_arrival(target)


        # ====================================================
        # ORDER SERVICE
        # ====================================================

        elif command == "TAKE_ORDER":

            return self.take_order(object_name)


        elif command == "CONFIRM_ORDER":

            return self.confirm_order(object_name)


        # ====================================================
        # OBJECT HANDLING
        # ====================================================

        elif command == "DETECT":

            return self.detect(object_name)


        elif command == "MOVE_TO_OBJECT":

            return self.move(object_name)


        elif command == "MOVE":

            return self.move(target)


        elif command == "GRAB":

            return self.grab(object_name)


        elif command == "RELEASE":

            return self.release(target)


        # ====================================================
        # DELIVERY
        # ====================================================

        elif command == "CONFIRM_DELIVERY":

            return self.confirm_delivery(target)


        elif command == "RETURN":

            return self.return_to_counter()


        # ====================================================
        # STOP
        # ====================================================

        elif command == "STOP":

            return self.stop()


        # ====================================================
        # UNKNOWN COMMAND
        # ====================================================

        else:

            return {
                "status": "FAILED",
                "message":
                    f"Unknown command: {command}"
            }


    # ========================================================
    # EXECUTE WITH RETRY
    # ========================================================

    def execute_with_retry(
        self,
        command,
        object_name="object",
        target="target"
    ):

        attempts = 0
        last_result = None

        while attempts < self.max_retries:

            attempts += 1

            result = self.execute_command(
                command,
                object_name,
                target
            )

            last_result = result

            if result["status"] == "SUCCESS":

                return {
                    "status": "SUCCESS",
                    "message": result["message"],
                    "attempts": attempts
                }

            print(
                f"⚠️ Attempt {attempts} failed."
            )

        return {

            "status": "FAILED",

            "message":
                last_result["message"]
                if last_result
                else "Execution failed.",

            "attempts": attempts
        }


    # ========================================================
    # EXECUTE COMPLETE SEQUENCE
    # ========================================================

    def execute_sequence(
        self,
        commands,
        object_name="object",
        target="target"
    ):

        results = []

        overall_status = "SUCCESS"

        # ----------------------------------------------------
        # Execute commands one by one
        # ----------------------------------------------------

        for index, command in enumerate(commands):

            command = command.upper()

            print(
                f"\n▶ Step {index + 1}: {command}"
            )

            # =================================================
            # MOVE COMMAND
            # =================================================

            if command == "MOVE":

                move_count = sum(
                    1
                    for r in results
                    if r["command"] == "MOVE"
                )

                # First MOVE = object
                # Second MOVE = target

                if move_count == 0:

                    move_destination = object_name

                else:

                    move_destination = target

                result = self.execute_with_retry(
                    "MOVE",
                    object_name=object_name,
                    target=move_destination
                )

            else:

                result = self.execute_with_retry(
                    command,
                    object_name=object_name,
                    target=target
                )

            # ------------------------------------------------
            # Save result
            # ------------------------------------------------

            results.append({

                "step": index + 1,

                "command": command,

                "status": result["status"],

                "message": result["message"],

                "attempts": result["attempts"]

            })

            # ------------------------------------------------
            # Stop if command fails completely
            # ------------------------------------------------

            if result["status"] == "FAILED":

                overall_status = "FAILED"

                break


        # ----------------------------------------------------
        # Final robot status
        # ----------------------------------------------------

        if overall_status == "SUCCESS":

            self.robot_status = "READY"

        else:

            self.robot_status = "ERROR"


        return {

            "overall_status":
                overall_status,

            "robot_status":
                self.robot_status,

            "current_location":
                self.current_location,

            "battery":
                self.battery,

            "current_order":
                self.current_order,

            "order_confirmed":
                self.order_confirmed,

            "results":
                results
        }


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 70)
    print("🤖 RESTAURANT ROBOT CONTROLLER TEST")
    print("=" * 70)


    # ========================================================
    # TEST 1 - CUSTOMER GREETING
    # ========================================================

    print("\n\nTEST 1: CUSTOMER GREETING")

    robot = RobotController()

    greeting_commands = [
        "DETECT_CUSTOMER",
        "GREET"
    ]

    greeting_result = robot.execute_sequence(
        greeting_commands,
        object_name="customer",
        target="counter"
    )

    print("\nResult:")
    print(greeting_result)


    # ========================================================
    # TEST 2 - SHOW MENU
    # ========================================================

    print("\n\nTEST 2: SHOW MENU")

    robot = RobotController()

    menu_commands = [
        "DETECT_CUSTOMER",
        "GREET",
        "SHOW_MENU"
    ]

    menu_result = robot.execute_sequence(
        menu_commands,
        object_name="customer",
        target="table 1"
    )

    print("\nResult:")
    print(menu_result)


    # ========================================================
    # TEST 3 - CUSTOMER ORDER
    # ========================================================

    print("\n\nTEST 3: CUSTOMER ORDER")

    robot = RobotController()

    order_commands = [
        "DETECT_CUSTOMER",
        "GREET",
        "TAKE_ORDER",
        "CONFIRM_ORDER"
    ]

    order_result = robot.execute_sequence(
        order_commands,
        object_name="pizza",
        target="table 1"
    )

    print("\nResult:")
    print(order_result)


    # ========================================================
    # TEST 4 - TABLE GUIDANCE
    # ========================================================

    print("\n\nTEST 4: GUIDE CUSTOMER")

    robot = RobotController()

    guide_commands = [
        "DETECT_CUSTOMER",
        "GREET",
        "ASSIGN_TABLE",
        "MOVE_TO_CUSTOMER",
        "GUIDE"
    ]

    guide_result = robot.execute_sequence(
        guide_commands,
        object_name="customer",
        target="table 3"
    )

    print("\nResult:")
    print(guide_result)


    # ========================================================
    # TEST 5 - FOOD DELIVERY
    # ========================================================

    print("\n\nTEST 5: FOOD DELIVERY")

    delivery_robot = RobotController()

    delivery_commands = [
        "DETECT",
        "MOVE",
        "GRAB",
        "MOVE",
        "RELEASE",
        "CONFIRM_DELIVERY",
        "RETURN"
    ]

    delivery_result = delivery_robot.execute_sequence(
        delivery_commands,
        object_name="water bottle",
        target="table 3"
    )

    print("\nResult:")
    print(delivery_result)


    # ========================================================
    # FINAL
    # ========================================================

    print("\n")

    print("=" * 70)
    print("✅ ROBOT CONTROLLER TEST COMPLETED")
    print("=" * 70)