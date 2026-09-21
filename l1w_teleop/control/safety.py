import time
from typing import Tuple
from dataclasses import replace

from .models import DogCommand, RobotCommands, SafetyState


class CommandSafetyGate:
    """Returns safe commands until startup, release, or input loss."""

    def __init__(self, startup_hold_s: float = 2.0):
        self._startup_hold_s = startup_hold_s
        self._started_ns = time.monotonic_ns()
        self._pending_dog_mode_command = ""

    def apply(
        self, commands: RobotCommands, input_healthy: bool
    ) -> Tuple[RobotCommands, SafetyState]:
        elapsed_s = (time.monotonic_ns() - self._started_ns) / 1_000_000_000
        startup_ok = elapsed_s >= self._startup_hold_s
        dog_mode_command = commands.dog_mode_command
        if not startup_ok and input_healthy and dog_mode_command:
            # Mapping emits mode transitions only on their button edge. Preserve
            # that edge instead of losing it while the startup hold is active.
            self._pending_dog_mode_command = dog_mode_command
        if startup_ok:
            dog_mode_command = dog_mode_command or self._pending_dog_mode_command
            self._pending_dog_mode_command = ""
        elif not input_healthy:
            self._pending_dog_mode_command = ""
            dog_mode_command = ""
        else:
            dog_mode_command = ""
        dog_enabled = input_healthy and startup_ok and commands.dog.enabled
        arm_enabled = input_healthy and startup_ok and commands.arm.enabled
        dog = commands.dog if dog_enabled else DogCommand(enabled=False)
        arm = replace(commands.arm, enabled=arm_enabled)
        state = SafetyState(
            input_healthy=input_healthy,
            dog_enabled=dog.enabled,
            arm_enabled=arm.enabled,
            elapsed_s=elapsed_s,
        )
        gated = replace(
            commands,
            dog=dog,
            arm=arm,
            dog_mode_command=dog_mode_command,
            arm_mode_command=commands.arm_mode_command if startup_ok else "",
        )
        return gated, state
