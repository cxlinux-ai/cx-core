import subprocess
import time
import json
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class InstallationStep:
    command: str
    description: str
    status: StepStatus = StepStatus.PENDING
    output: str = ""
    error: str = ""
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    return_code: Optional[int] = None
    
    def duration(self) -> Optional[float]:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None


@dataclass
class InstallationResult:
    success: bool
    steps: List[InstallationStep]
    total_duration: float
    failed_step: Optional[int] = None
    error_message: Optional[str] = None


class InstallationCoordinator:
    """Coordinates multi-step software installation processes."""

    def __init__(
        self,
        commands: List[str],
        descriptions: Optional[List[str]] = None,
        timeout: int = 300,
        stop_on_error: bool = True,
        enable_rollback: bool = False,
        log_file: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, InstallationStep], None]] = None
    ):
        """Initialize an installation run with optional logging and rollback."""
        self.timeout = timeout
        self.stop_on_error = stop_on_error
        self.enable_rollback = enable_rollback
        self.log_file = log_file
        self.progress_callback = progress_callback
        
        if descriptions and len(descriptions) != len(commands):
            raise ValueError("Number of descriptions must match number of commands")
        
        self.steps = [
            InstallationStep(
                command=cmd,
                description=descriptions[i] if descriptions else f"Step {i+1}"
            )
            for i, cmd in enumerate(commands)
        ]
        
        self.rollback_commands: List[str] = []

    @classmethod
    def from_plan(
        cls,
        plan: List[Dict[str, str]],
        *,
        timeout: int = 300,
        stop_on_error: bool = True,
        enable_rollback: Optional[bool] = None,
        log_file: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, InstallationStep], None]] = None
    ) -> "InstallationCoordinator":
        """Create a coordinator from a structured plan produced by an LLM.

        Each plan entry should contain at minimum a ``command`` key and
        optionally ``description`` and ``rollback`` fields. Rollback commands are
        registered automatically when present.
        """

        commands: List[str] = []
        descriptions: List[str] = []
        rollback_commands: List[str] = []

        for index, step in enumerate(plan):
            command = step.get("command")
            if not command:
                raise ValueError("Each plan step must include a 'command'")

            commands.append(command)
            descriptions.append(step.get("description", f"Step {index + 1}"))

            rollback_cmd = step.get("rollback")
            if rollback_cmd:
                rollback_commands.append(rollback_cmd)

        coordinator = cls(
            commands,
            descriptions,
            timeout=timeout,
            stop_on_error=stop_on_error,
            enable_rollback=enable_rollback if enable_rollback is not None else bool(rollback_commands),
            log_file=log_file,
            progress_callback=progress_callback,
        )

        for rollback_cmd in rollback_commands:
            coordinator.add_rollback_command(rollback_cmd)

        return coordinator
    
    def _log(self, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        
        if self.log_file:
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(log_entry + '\n')
            except Exception:
                pass
    
    def _execute_command(self, step: InstallationStep) -> bool:
        step.status = StepStatus.RUNNING
        step.start_time = time.time()
        
        self._log(f"Executing: {step.command}")
        
        try:
            result = subprocess.run(
                step.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            step.return_code = result.returncode
            step.output = result.stdout
            step.error = result.stderr
            step.end_time = time.time()
            
            if result.returncode == 0:
                step.status = StepStatus.SUCCESS
                self._log(f"Success: {step.command}")
                return True
            else:
                step.status = StepStatus.FAILED
                self._log(f"Failed: {step.command} (exit code: {result.returncode})")
                return False
                
        except subprocess.TimeoutExpired:
            step.status = StepStatus.FAILED
            step.error = f"Command timed out after {self.timeout} seconds"
            step.end_time = time.time()
            self._log(f"Timeout: {step.command}")
            return False
            
        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)
            step.end_time = time.time()
            self._log(f"Error: {step.command} - {str(e)}")
            return False
    
    def _rollback(self):
        if not self.enable_rollback or not self.rollback_commands:
            return
        
        self._log("Starting rollback...")
        
        for cmd in reversed(self.rollback_commands):
            try:
                self._log(f"Rollback: {cmd}")
                subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    timeout=self.timeout
                )
            except Exception as e:
                self._log(f"Rollback failed: {cmd} - {str(e)}")
    
    def add_rollback_command(self, command: str):
        """Register a rollback command executed if a step fails."""
        self.rollback_commands.append(command)
    
    def execute(self) -> InstallationResult:
        """Run each installation step and capture structured results."""
        start_time = time.time()
        failed_step_index = None
        
        self._log(f"Starting installation with {len(self.steps)} steps")
        
        for i, step in enumerate(self.steps):
            if self.progress_callback:
                self.progress_callback(i + 1, len(self.steps), step)
            
            success = self._execute_command(step)
            
            if not success:
                failed_step_index = i
                if self.stop_on_error:
                    for remaining_step in self.steps[i+1:]:
                        remaining_step.status = StepStatus.SKIPPED
                    
                    if self.enable_rollback:
                        self._rollback()
                    
                    total_duration = time.time() - start_time
                    self._log(f"Installation failed at step {i+1}")
                    
                    return InstallationResult(
                        success=False,
                        steps=self.steps,
                        total_duration=total_duration,
                        failed_step=i,
                        error_message=step.error or "Command failed"
                    )
        
        total_duration = time.time() - start_time
        all_success = all(s.status == StepStatus.SUCCESS for s in self.steps)
        
        if all_success:
            self._log("Installation completed successfully")
        else:
            self._log("Installation completed with errors")
        
        return InstallationResult(
            success=all_success,
            steps=self.steps,
            total_duration=total_duration,
            failed_step=failed_step_index,
            error_message=self.steps[failed_step_index].error if failed_step_index is not None else None
        )
    
    def verify_installation(self, verify_commands: List[str]) -> Dict[str, bool]:
        """Execute verification commands and return per-command success."""
        verification_results = {}
        
        self._log("Starting verification...")
        
        for cmd in verify_commands:
            try:
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                success = result.returncode == 0
                verification_results[cmd] = success
                self._log(f"Verification {cmd}: {'PASS' if success else 'FAIL'}")
            except Exception as e:
                verification_results[cmd] = False
                self._log(f"Verification {cmd}: ERROR - {str(e)}")
        
        return verification_results
    
    def get_summary(self) -> Dict[str, Any]:
        total_steps = len(self.steps)
        success_steps = sum(1 for s in self.steps if s.status == StepStatus.SUCCESS)
        failed_steps = sum(1 for s in self.steps if s.status == StepStatus.FAILED)
        skipped_steps = sum(1 for s in self.steps if s.status == StepStatus.SKIPPED)
        
        return {
            "total_steps": total_steps,
            "success": success_steps,
            "failed": failed_steps,
            "skipped": skipped_steps,
            "steps": [
                {
                    "command": s.command,
                    "description": s.description,
                    "status": s.status.value,
                    "duration": s.duration(),
                    "return_code": s.return_code
                }
                for s in self.steps
            ]
        }
    
    def export_log(self, filepath: str):
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.get_summary(), f, indent=2)


def install_docker() -> InstallationResult:
    plan = [
        {
            "command": "apt update",
            "description": "Update package lists"
        },
        {
            "command": "apt install -y apt-transport-https ca-certificates curl software-properties-common",
            "description": "Install dependencies"
        },
        {
            "command": "install -m 0755 -d /etc/apt/keyrings",
            "description": "Create keyrings directory"
        },
        {
            "command": "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg",
            "description": "Add Docker GPG key"
        },
        {
            "command": "chmod a+r /etc/apt/keyrings/docker.gpg",
            "description": "Set key permissions"
        },
        {
            "command": 'echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null',
            "description": "Add Docker repository"
        },
        {
            "command": "apt update",
            "description": "Update package lists again"
        },
        {
            "command": "apt install -y docker-ce docker-ce-cli containerd.io",
            "description": "Install Docker packages"
        },
        {
            "command": "systemctl start docker",
            "description": "Start Docker service",
            "rollback": "systemctl stop docker"
        },
        {
            "command": "systemctl enable docker",
            "description": "Enable Docker on boot",
            "rollback": "systemctl disable docker"
        }
    ]

    coordinator = InstallationCoordinator.from_plan(plan, timeout=300, stop_on_error=True)
    
    result = coordinator.execute()
    
    if result.success:
        verify_commands = ["docker --version", "systemctl is-active docker"]
        coordinator.verify_installation(verify_commands)
    
    return result


def example_cuda_install_plan() -> List[Dict[str, str]]:
    """Return a sample CUDA installation plan for LLM integration tests."""

    return [
        {
            "command": "apt update",
            "description": "Refresh package repositories"
        },
        {
            "command": "apt install -y build-essential dkms",
            "description": "Install build tooling"
        },
        {
            "command": "sh cuda_installer.run --silent",
            "description": "Install CUDA drivers",
            "rollback": "rm -rf /usr/local/cuda"
        },
        {
            "command": "nvidia-smi",
            "description": "Verify GPU driver status"
        },
        {
            "command": "nvcc --version",
            "description": "Validate CUDA compiler installation"
        }
    ]
