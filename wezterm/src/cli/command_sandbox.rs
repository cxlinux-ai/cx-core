/*
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1
*/

//! Run shell snippets from `cx ask` inside an optional OS sandbox when available.

use anyhow::{Context, Result};
use std::path::Path;
use std::process::{Command, ExitStatus};

/// Which sandbox wrapper was selected (if any).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SandboxBackend {
    Firejail,
    Bubblewrap,
    /// Neither `firejail` nor `bwrap` is on PATH — caller must warn before running on host.
    None,
}

/// Resolve sandbox backend once per process (PATH is static for our purposes).
pub fn detect_sandbox_backend() -> SandboxBackend {
    if path_exists_executable("firejail") {
        SandboxBackend::Firejail
    } else if path_exists_executable("bwrap") {
        SandboxBackend::Bubblewrap
    } else {
        SandboxBackend::None
    }
}

fn path_exists_executable(name: &str) -> bool {
    let paths = std::env::var_os("PATH").unwrap_or_default();
    std::env::split_paths(&paths).any(|dir| {
        let candidate = dir.join(name);
        candidate.is_file() && is_executable(&candidate)
    })
}

#[cfg(unix)]
fn is_executable(path: &Path) -> bool {
    use std::os::unix::fs::PermissionsExt;
    path.metadata()
        .map(|m| m.permissions().mode() & 0o111 != 0)
        .unwrap_or(false)
}

#[cfg(not(unix))]
fn is_executable(path: &Path) -> bool {
    path.is_file()
}

/// Human-readable label for audit logs and stderr.
pub fn sandbox_backend_label(backend: SandboxBackend) -> &'static str {
    match backend {
        SandboxBackend::Firejail => "firejail",
        SandboxBackend::Bubblewrap => "bubblewrap",
        SandboxBackend::None => "none",
    }
}

/// Detect if a command requires privileged package manager operations that cannot run in sandbox.
/// These commands should bypass the sandbox after explicit user confirmation.
fn is_privileged_package_command(command: &str) -> bool {
    let cmd = command.trim();

    // Check for sudo followed by package manager commands
    if cmd.starts_with("sudo ") {
        let after_sudo = &cmd[5..].trim_start();
        return after_sudo.starts_with("apt ")
            || after_sudo.starts_with("apt-get ")
            || after_sudo.starts_with("dpkg ")
            || after_sudo.starts_with("snap ");
    }

    false
}

/// Run `command` under a sandbox when possible; otherwise run on the host after emitting a warning.
pub fn run_sandboxed_shell(command: &str) -> Result<ExitStatus> {
    run_sandboxed_shell_in(command, None)
}

/// Run `command` in `cwd` when provided (undo uses the original working directory).
pub fn run_sandboxed_shell_in(command: &str, cwd: Option<&Path>) -> Result<ExitStatus> {
    if std::env::var_os("CX_DISABLE_SANDBOX").is_some() {
        eprintln!("WARNING: CX_DISABLE_SANDBOX is set; running on host without sandbox.");
        return run_host_shell_in(command, cwd);
    }

    // Privileged package manager commands cannot run inside sandbox due to:
    // - firejail: --caps.drop=all denies sudo
    // - bwrap: --unshare-all sets no-new-privileges flag, blocking sudo
    // These commands run on the host after explicit confirmation.
    if is_privileged_package_command(command) {
        eprintln!("NOTE: Privileged package manager command detected.");
        eprintln!("      This command will run on the HOST (not sandboxed) after confirmation.");
        return run_host_shell_in(command, cwd);
    }

    let backend = detect_sandbox_backend();
    match backend {
        SandboxBackend::Firejail => run_firejail_in(command, cwd),
        SandboxBackend::Bubblewrap => run_bubblewrap_in(command, cwd),
        SandboxBackend::None => {
            eprintln!("WARNING: Neither firejail nor bubblewrap (bwrap) was found on PATH.");
            eprintln!(
                "         Command will run on the host without a sandbox. Install firejail or bubblewrap for isolation."
            );
            run_host_shell_in(command, cwd)
        }
    }
}

fn apply_cwd(cmd: &mut Command, cwd: Option<&Path>) -> Result<()> {
    if let Some(dir) = cwd {
        cmd.current_dir(dir);
    }
    Ok(())
}

fn run_host_shell_in(command: &str, cwd: Option<&Path>) -> Result<ExitStatus> {
    let mut cmd = Command::new("sh");
    cmd.arg("-c").arg(command);
    apply_cwd(&mut cmd, cwd)?;
    cmd.status().context("failed to run shell command on host")
}

/// Conservative firejail profile: private tmp, no network, drop caps, then user command.
/// Working directory is inherited through apply_cwd (firejail preserves the host cwd by default).
fn run_firejail_in(command: &str, cwd: Option<&Path>) -> Result<ExitStatus> {
    eprintln!("(sandbox: firejail — private-tmp, net=none, caps dropped)");

    // Resolve the working directory for validation
    let working_dir = if let Some(dir) = cwd {
        dir.to_path_buf()
    } else {
        std::env::current_dir().context("failed to get current directory")?
    };

    if !working_dir.exists() {
        anyhow::bail!(
            "Working directory does not exist: {}. Cannot create safe sandbox.",
            working_dir.display()
        );
    }

    let mut cmd = Command::new("firejail");
    cmd.args([
        "--quiet",
        "--private-tmp",
        "--net=none",
        "--caps.drop=all",
        "--",
        "sh",
        "-c",
        command,
    ]);
    apply_cwd(&mut cmd, Some(&working_dir))?;
    cmd.status().context("firejail failed to start")
}

/// Minimal bubblewrap: read-only system roots, writable /tmp, no new privileges.
/// Binds the current working directory as read-write and HOME as read-only.
fn run_bubblewrap_in(command: &str, cwd: Option<&Path>) -> Result<ExitStatus> {
    eprintln!("(sandbox: bubblewrap — read-only bind mounts, tmpfs /tmp, cwd+home bound)");

    // Resolve the working directory
    let working_dir = if let Some(dir) = cwd {
        dir.to_path_buf()
    } else {
        std::env::current_dir().context("failed to get current directory")?
    };

    let mut cmd = Command::new("bwrap");

    // Read-only system directories
    for bind in ["/usr", "/bin", "/lib", "/lib64", "/etc", "/sbin"] {
        if Path::new(bind).exists() {
            cmd.args(["--ro-bind", bind, bind]);
        }
    }

    // Bind current working directory as read-write so file operations work
    if working_dir.exists() {
        cmd.args([
            "--bind",
            working_dir
                .to_str()
                .context("cwd path is not valid UTF-8")?,
            working_dir
                .to_str()
                .context("cwd path is not valid UTF-8")?,
        ]);
    } else {
        anyhow::bail!(
            "Working directory does not exist: {}. Cannot create safe sandbox.",
            working_dir.display()
        );
    }

    // Bind HOME as read-only if it exists and is different from cwd
    if let Some(home) = dirs::home_dir() {
        if home.exists() && home != working_dir {
            cmd.args([
                "--ro-bind",
                home.to_str().context("home path is not valid UTF-8")?,
                home.to_str().context("home path is not valid UTF-8")?,
            ]);
        }
    }

    cmd.args([
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--die-with-parent",
        "--unshare-all",
        "--chdir",
        working_dir
            .to_str()
            .context("cwd path is not valid UTF-8")?,
        "--",
        "sh",
        "-c",
        command,
    ]);

    apply_cwd(&mut cmd, Some(&working_dir))?;
    cmd.status().context("bubblewrap failed to start")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn backend_label_strings() {
        assert_eq!(sandbox_backend_label(SandboxBackend::Firejail), "firejail");
        assert_eq!(sandbox_backend_label(SandboxBackend::None), "none");
    }

    #[test]
    fn detect_does_not_panic() {
        let _ = detect_sandbox_backend();
    }

    #[test]
    fn privileged_package_commands_detected() {
        assert!(is_privileged_package_command("sudo apt install docker"));
        assert!(is_privileged_package_command("sudo apt-get install hello"));
        assert!(is_privileged_package_command("sudo dpkg -i package.deb"));
        assert!(is_privileged_package_command("sudo snap install code"));
        assert!(is_privileged_package_command("sudo apt update"));
    }

    #[test]
    fn non_privileged_commands_not_detected() {
        assert!(!is_privileged_package_command("apt-cache search hello"));
        assert!(!is_privileged_package_command("which apt"));
        assert!(!is_privileged_package_command("echo 'sudo apt install'"));
        assert!(!is_privileged_package_command("ls -la"));
        assert!(!is_privileged_package_command(
            "sudo systemctl restart docker"
        ));
    }

    #[test]
    fn privileged_requires_sudo_prefix() {
        // Without sudo, these should not be treated as privileged
        assert!(!is_privileged_package_command("apt install hello"));
        assert!(!is_privileged_package_command("apt-get update"));
    }
}
