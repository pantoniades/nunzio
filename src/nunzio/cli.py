"""Interactive CLI for Nunzio workout assistant."""

import asyncio
import sys

from .core import MessageHandler


class NunzioCLI:
    """CLI wrapper around the shared message handler."""

    def __init__(self) -> None:
        self._handler = MessageHandler()

    async def run(self) -> None:
        await self._handler.initialize()
        print("Connected to database and LLM.")
        print("Nunzio Workout Assistant")
        print("Type 'help' for commands or 'exit' to quit.")
        print("-" * 50)

        while True:
            try:
                user_input = input("You: ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ("exit", "quit", "bye"):
                    print("Goodbye!")
                    break
                if user_input.lower() == "help":
                    self._show_help()
                    continue

                response = await self._handler.process(user_input)
                print(f"Nunzio: {response}")
                print("-" * 50)

            except (KeyboardInterrupt, EOFError):
                print("\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {e}")
                continue

        await self._handler.close()

    def _show_help(self) -> None:
        print(
            "Nunzio Commands:\n"
            "\n"
            "  Log a workout:\n"
            '    "I did 3 sets of bench press at 185 lbs, 10 reps"\n'
            '    "squat 5x5 at 225 lbs"\n'
            "\n"
            "  View stats:\n"
            '    "show my stats"\n'
            '    "how have my workouts been?"\n'
            "\n"
            "  Get recommendations:\n"
            '    "what should I do for chest?"\n'
            '    "suggest some leg exercises"\n'
            "\n"
            "  help  - show this message\n"
            "  exit  - quit"
        )


async def main() -> None:
    cli = NunzioCLI()
    await cli.run()


def main_sync() -> None:
    """Entry point for pyproject.toml console_scripts."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main_sync()
