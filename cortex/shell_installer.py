import os
from pathlib import Path

BASH_MARKER = "# >>> cortex shell integration >>>"
ZSH_MARKER = "# >>> cortex shell integration >>>"


def _append_if_missing(rc_path: Path, block: str) -> bool:
    if rc_path.exists():
        content = rc_path.read_text()
        if BASH_MARKER in content:
            return False
    else:
        rc_path.touch()

    with rc_path.open("a", encoding="utf-8") as f:
        f.write("\n" + block + "\n")

    return True


def install_shell_integration() -> str:
    shell = os.environ.get("SHELL", "")
    home = Path.home()

    if shell.endswith("bash"):
        rc = home / ".bashrc"
        script_path = Path(__file__).resolve().parent.parent / "scripts" / "cortex_bash.sh"
        block = f"""{BASH_MARKER}
source "{script_path}"
# <<< cortex shell integration <<<
"""
        installed = _append_if_missing(rc, block)
        return "bash", installed

    elif shell.endswith("zsh"):
        rc = home / ".zshrc"
        script_path = Path(__file__).resolve().parent.parent / "scripts" / "cortex_zsh.zsh"
        block = f"""{ZSH_MARKER}
source "{script_path}"
# <<< cortex shell integration <<<
"""
        installed = _append_if_missing(rc, block)
        return "zsh", installed

    else:
        raise RuntimeError("Unsupported shell. Only bash and zsh are supported.")
