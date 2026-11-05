/*
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1
You may not use this file except in compliance with the License.
*/

//! CX Terminal: dry-run-by-default guard for package-changing commands.
//!
//! Every command that would install, remove or upgrade system packages goes through
//! [`guard`] before it runs:
//!
//! 1. **Classify** the command text. Only a single, plain invocation of `apt`,
//!    `apt-get`, `dpkg` or `snap` (optionally prefixed by `sudo`) is accepted. A
//!    package manager hidden in a pipeline, subshell, redirect or `;` list is refused,
//!    because its effect can't be previewed.
//! 2. **Preview** with `apt-get -s` (no root needed, nothing changes) and show the
//!    exact packages that would be installed, upgraded or removed. If the simulation
//!    fails, or there is nothing to do, nothing runs. `dpkg`/`snap` have no simulation;
//!    the preview says so and shows the exact command.
//! 3. **Confirm**: `[y/N]`, default No; EOF (no terminal) is No. Only an explicit
//!    `-y` given by the user skips the prompt; the preview is still shown.
//! 4. **Run** the exact argv (no shell), then **record** it in `~/.cx/audit.log`
//!    and, when it can be reversed, in `~/.cx/transactions.jsonl` with the undo
//!    command (`apt-get remove` of what was newly installed, `apt-get install` of
//!    what was removed).
//!
//! The process runner is a trait so tests prove the guarantees without touching the
//! system: nothing executes unless the user consented after a successful preview.
//!
//! This is the bar for any code path that changes packages (including contributor
//! PRs #763/#764): build the command text, then call `guard` — never `sh -c` it.

use anyhow::{Context, Result};
use serde::Serialize;
use std::fs::{self, OpenOptions};
use std::io::{BufRead, Write};
use std::path::{Path, PathBuf};
use std::process::Command;

/// Package manager being invoked.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum Manager {
    Apt,
    Dpkg,
    Snap,
}

/// A command that changes packages, parsed into argv.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PackageCommand {
    pub manager: Manager,
    /// Normalized action: install, reinstall, remove, purge, autoremove, upgrade,
    /// dist-upgrade (apt); install / remove (dpkg, snap); refresh (snap).
    pub action: String,
    /// Exact argv that will run, including `sudo` if the user wrote it.
    pub argv: Vec<String>,
    /// Package names / files named on the command line (may be empty for upgrades).
    pub targets: Vec<String>,
    /// For apt: argv of the equivalent `apt-get -s` simulation.
    pub simulation: Option<Vec<String>>,
}

/// Result of classifying arbitrary command text.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Classification {
    /// Does not change packages; handled by the normal confirmation path.
    NotPackage,
    /// A plain package-changing command the guard can preview.
    Package(PackageCommand),
    /// Changes (or may change) packages in a form that cannot be previewed safely.
    Refused(String),
}

/// What the simulation says will happen.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct Plan {
    pub install: Vec<String>,
    pub upgrade: Vec<String>,
    pub remove: Vec<String>,
    /// False for dpkg/snap, which have no dry-run mode.
    pub simulated: bool,
}

impl Plan {
    pub fn is_empty(&self) -> bool {
        self.install.is_empty() && self.upgrade.is_empty() && self.remove.is_empty()
    }

    /// Command that reverses this plan, if one exists. Upgrades can't be reversed
    /// reliably (old versions may be gone from the archive), so they return `None`.
    pub fn undo_command(&self) -> Option<String> {
        if !self.simulated || !self.upgrade.is_empty() {
            return None;
        }
        match (self.install.is_empty(), self.remove.is_empty()) {
            (false, true) => Some(format!("sudo apt-get remove {}", self.install.join(" "))),
            (true, false) => Some(format!("sudo apt-get install {}", self.remove.join(" "))),
            _ => None,
        }
    }
}

/// How the user consented.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Consent {
    /// Ask `[y/N]` after the preview.
    Prompt,
    /// The user passed `-y` explicitly; the preview is still shown.
    Explicit,
}

/// Final outcome of [`guard`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Outcome {
    Executed { success: bool, code: Option<i32> },
    Declined,
    NothingToDo,
    PreviewFailed(String),
    Refused(String),
}

/// Output of a simulation.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SimOutput {
    pub success: bool,
    pub stdout: String,
    pub stderr: String,
}

/// Runs processes. Real implementation: [`SystemRunner`].
pub trait Runner {
    fn simulate(&mut self, argv: &[String]) -> Result<SimOutput>;
    fn execute(&mut self, argv: &[String]) -> Result<(bool, Option<i32>)>;
}

/// Runs real processes, never through a shell.
pub struct SystemRunner;

impl Runner for SystemRunner {
    fn simulate(&mut self, argv: &[String]) -> Result<SimOutput> {
        let out = Command::new(&argv[0])
            .args(&argv[1..])
            .env("LC_ALL", "C")
            .output()
            .with_context(|| format!("failed to start {}", argv[0]))?;
        Ok(SimOutput {
            success: out.status.success(),
            stdout: String::from_utf8_lossy(&out.stdout).into_owned(),
            stderr: String::from_utf8_lossy(&out.stderr).into_owned(),
        })
    }

    fn execute(&mut self, argv: &[String]) -> Result<(bool, Option<i32>)> {
        let status = Command::new(&argv[0])
            .args(&argv[1..])
            .status()
            .with_context(|| format!("failed to start {}", argv[0]))?;
        Ok((status.success(), status.code()))
    }
}

const PACKAGE_TOOLS: &[&str] = &["apt", "apt-get", "aptitude", "dpkg", "snap"];
const SHELL_META: &[&str] = &[";", "|", "&", "`", "$(", ">", "<", "\n", "(", ")"];

/// True if any word of the text names a package tool (cheap pre-check).
fn mentions_package_tool(text: &str) -> bool {
    text.split(|c: char| c.is_whitespace() || ";|&()`$<>".contains(c))
        .map(|w| w.rsplit('/').next().unwrap_or(w))
        .any(|w| PACKAGE_TOOLS.contains(&w))
}

/// Split `a && b && c` into its parts when `&&` is the only shell operator, so a
/// common AI answer like `sudo apt update && sudo apt install -y nginx` is handled as
/// two commands, each guarded on its own. Returns the input unchanged otherwise.
pub fn split_and_chain(text: &str) -> Vec<String> {
    let parts: Vec<String> = text.split("&&").map(|p| p.trim().to_string()).collect();
    if parts.len() > 1
        && parts
            .iter()
            .all(|p| !p.is_empty() && !SHELL_META.iter().any(|m| p.contains(m)))
    {
        parts
    } else {
        vec![text.trim().to_string()]
    }
}

/// Classify one command (already split on `&&`).
pub fn classify(text: &str) -> Classification {
    let text = text.trim();
    if !mentions_package_tool(text) {
        return Classification::NotPackage;
    }
    if SHELL_META.iter().any(|m| text.contains(m)) {
        return Classification::Refused(
            "this command combines a package manager with shell operators, so its effect \
             can't be previewed. Run the package step on its own."
                .into(),
        );
    }
    let words = match shell_words::split(text) {
        Ok(w) if !w.is_empty() => w,
        _ => return Classification::Refused("could not parse the command safely".into()),
    };

    let mut idx = 0;
    if words[0] == "sudo" {
        idx = 1;
        if words.get(1).map_or(false, |w| w.starts_with('-')) {
            return Classification::Refused("sudo options are not supported here".into());
        }
    }
    if words.get(idx).map_or(false, |w| w.contains('=')) {
        return Classification::Refused(
            "environment assignments before a package command are not supported".into(),
        );
    }
    let tool = match words.get(idx) {
        Some(t) => t.rsplit('/').next().unwrap_or(t).to_string(),
        None => return Classification::NotPackage,
    };
    let rest = &words[idx + 1..];

    match tool.as_str() {
        "apt" | "apt-get" => classify_apt(&words, rest),
        "aptitude" => Classification::Refused(
            "aptitude is not supported; use apt so the change can be previewed".into(),
        ),
        "dpkg" => classify_dpkg(&words, rest),
        "snap" => classify_snap(&words, rest),
        // A package tool is mentioned only as an argument (e.g. `man apt`).
        _ => Classification::NotPackage,
    }
}

/// apt options whose value is the next word.
const APT_VALUE_OPTIONS: &[&str] = &[
    "-o",
    "--option",
    "-c",
    "--config-file",
    "-t",
    "--target-release",
];

fn classify_apt(argv: &[String], rest: &[String]) -> Classification {
    // Find the action first so read-only commands with any options (`apt list
    // --installed`) stay ordinary commands. Values of value-taking options are skipped
    // so `-o X install` can't hide the action.
    let mut skip_next = false;
    let first_word = rest.iter().find(|w| {
        if skip_next {
            skip_next = false;
            return false;
        }
        if APT_VALUE_OPTIONS.contains(&w.as_str()) {
            skip_next = true;
            return false;
        }
        !w.starts_with('-')
    });
    let changes_packages = matches!(
        first_word.map(String::as_str),
        Some(
            "install"
                | "reinstall"
                | "remove"
                | "purge"
                | "autoremove"
                | "upgrade"
                | "dist-upgrade"
                | "full-upgrade"
        )
    );
    if !changes_packages {
        return Classification::NotPackage;
    }

    let mut action: Option<&str> = None;
    let mut flags = Vec::new();
    let mut targets = Vec::new();
    for w in rest {
        if w.starts_with('-') {
            match w.as_str() {
                "-y" | "--yes" | "--assume-yes" | "-q" | "-qq" | "--quiet" => {}
                "--no-install-recommends"
                | "--install-recommends"
                | "--install-suggests"
                | "--no-install-suggests"
                | "--only-upgrade"
                | "--reinstall"
                | "--purge"
                | "--fix-broken"
                | "-f"
                | "--fix-missing"
                | "-m" => flags.push(w.clone()),
                other => {
                    return Classification::Refused(format!(
                        "apt option {} is not supported here; run the command yourself",
                        other
                    ))
                }
            }
        } else if action.is_none() {
            action = Some(w.as_str());
        } else {
            targets.push(w.clone());
        }
    }

    let action = match action {
        Some(a) => a,
        None => return Classification::NotPackage,
    };
    let sim_action = match action {
        "install" | "reinstall" | "remove" | "purge" | "autoremove" | "upgrade"
        | "dist-upgrade" => action,
        "full-upgrade" => "dist-upgrade",
        // update, search, show, list, policy, ... do not change installed packages.
        _ => return Classification::NotPackage,
    };
    if matches!(sim_action, "install" | "reinstall" | "remove" | "purge") && targets.is_empty() {
        return Classification::Refused(format!("`{}` needs at least one package", action));
    }
    if let Some(bad) = targets.iter().find(|t| !is_package_arg(t)) {
        return Classification::Refused(format!("`{}` is not a plain package name", bad));
    }

    let mut simulation = vec!["apt-get".to_string(), "-s".to_string()];
    simulation.extend(flags);
    simulation.push(sim_action.to_string());
    simulation.extend(targets.iter().cloned());

    Classification::Package(PackageCommand {
        manager: Manager::Apt,
        action: sim_action.to_string(),
        argv: argv.to_vec(),
        targets,
        simulation: Some(simulation),
    })
}

fn classify_dpkg(argv: &[String], rest: &[String]) -> Classification {
    let action = match rest.first().map(String::as_str) {
        Some("-i") | Some("--install") => "install",
        Some("-r") | Some("--remove") | Some("-P") | Some("--purge") => "remove",
        // -l, -L, -s, -S, --get-selections ... are read-only.
        _ => return Classification::NotPackage,
    };
    let targets: Vec<String> = rest[1..].to_vec();
    if targets.is_empty() || targets.iter().any(|t| t.starts_with('-')) {
        return Classification::Refused("dpkg needs plain package names or .deb files".into());
    }
    Classification::Package(PackageCommand {
        manager: Manager::Dpkg,
        action: action.into(),
        argv: argv.to_vec(),
        targets,
        simulation: None,
    })
}

fn classify_snap(argv: &[String], rest: &[String]) -> Classification {
    let action = match rest.first().map(String::as_str) {
        Some(a @ ("install" | "remove" | "refresh" | "revert")) => a,
        _ => return Classification::NotPackage,
    };
    Classification::Package(PackageCommand {
        manager: Manager::Snap,
        action: action.into(),
        argv: argv.to_vec(),
        targets: rest[1..]
            .iter()
            .filter(|t| !t.starts_with('-'))
            .cloned()
            .collect(),
        simulation: None,
    })
}

/// Package name, optionally with `=version`, `/release` or `:arch`, or a local .deb.
fn is_package_arg(s: &str) -> bool {
    !s.is_empty()
        && !s.starts_with('-')
        && s.chars().all(|c| {
            c.is_ascii_alphanumeric() || matches!(c, '.' | '_' | '+' | '-' | ':' | '=' | '/' | '~')
        })
}

/// Parse `apt-get -s` output (`Inst`, `Remv`, `Purg` lines).
pub fn parse_simulation(stdout: &str) -> Plan {
    let mut plan = Plan {
        simulated: true,
        ..Plan::default()
    };
    for line in stdout.lines() {
        let mut parts = line.split_whitespace();
        let kind = parts.next();
        let name = match parts.next() {
            Some(n) => n.to_string(),
            None => continue,
        };
        match kind {
            // `Inst pkg [old] (new ...)` is an upgrade; `Inst pkg (new ...)` is new.
            Some("Inst") => {
                if parts.next().map_or(false, |w| w.starts_with('[')) {
                    plan.upgrade.push(name);
                } else {
                    plan.install.push(name);
                }
            }
            Some("Remv") | Some("Purg") => plan.remove.push(name),
            _ => {}
        }
    }
    plan
}

/// Render the preview shown before consent.
pub fn render_preview(cmd: &PackageCommand, plan: &Plan) -> String {
    let mut out = format!("\nPackage change preview for: {}\n", cmd.argv.join(" "));
    if !plan.simulated {
        out.push_str(&format!(
            "  {:?} has no dry-run mode; nothing below was simulated.\n  It will run exactly the command above.\n",
            cmd.manager
        ));
        return out;
    }
    let section = |out: &mut String, label: &str, items: &[String]| {
        if !items.is_empty() {
            out.push_str(&format!(
                "  {} ({}): {}\n",
                label,
                items.len(),
                items.join(" ")
            ));
        }
    };
    section(&mut out, "Install", &plan.install);
    section(&mut out, "Upgrade", &plan.upgrade);
    section(&mut out, "Remove", &plan.remove);
    if plan.is_empty() {
        out.push_str("  Nothing to change.\n");
    }
    out.push_str("  (simulated with apt-get -s; nothing has changed yet)\n");
    out
}

/// Preview, confirm, run and record one package command.
///
/// `answer` supplies the user's reply to `[y/N]`; `None` means EOF.
pub fn guard<R: Runner, W: Write>(
    cmd: &PackageCommand,
    consent: Consent,
    runner: &mut R,
    answer: &mut dyn FnMut() -> Option<String>,
    out: &mut W,
    data_dir: Option<&Path>,
) -> Result<Outcome> {
    let plan = match &cmd.simulation {
        Some(sim) => {
            let result = runner.simulate(sim)?;
            if !result.success {
                let reason = result
                    .stderr
                    .lines()
                    .chain(result.stdout.lines())
                    .find(|l| l.starts_with("E:"))
                    .unwrap_or("simulation failed")
                    .to_string();
                writeln!(out, "\nPreview failed, nothing was run: {}", reason)?;
                record(
                    data_dir,
                    "package_preview_failed",
                    cmd,
                    &Plan::default(),
                    None,
                )?;
                return Ok(Outcome::PreviewFailed(reason));
            }
            parse_simulation(&result.stdout)
        }
        None => Plan::default(),
    };

    write!(out, "{}", render_preview(cmd, &plan))?;

    if plan.simulated && plan.is_empty() {
        writeln!(out, "Nothing to do; not running.")?;
        record(data_dir, "package_nothing_to_do", cmd, &plan, None)?;
        return Ok(Outcome::NothingToDo);
    }

    let approved = match consent {
        Consent::Explicit => true,
        Consent::Prompt => {
            write!(out, "\nApply these package changes? [y/N] ")?;
            out.flush()?;
            match answer() {
                Some(a) => matches!(a.trim(), "y" | "Y" | "yes" | "YES" | "Yes"),
                None => {
                    writeln!(out, "\nNo interactive input; not running.")?;
                    false
                }
            }
        }
    };
    if !approved {
        writeln!(out, "Cancelled. No packages were changed.")?;
        record(data_dir, "package_declined", cmd, &plan, None)?;
        return Ok(Outcome::Declined);
    }

    writeln!(out, "$ {}", cmd.argv.join(" "))?;
    let (success, code) = runner.execute(&cmd.argv)?;
    let undo = if success { plan.undo_command() } else { None };
    record(
        data_dir,
        if success {
            "package_executed"
        } else {
            "package_failed"
        },
        cmd,
        &plan,
        undo.as_deref(),
    )?;
    if success {
        if let Some(u) = &undo {
            writeln!(out, "Recorded. To reverse: {}", u)?;
        }
    } else {
        writeln!(out, "Command failed with exit code: {:?}", code)?;
    }
    Ok(Outcome::Executed { success, code })
}

/// Read one line from stdin; `None` at EOF.
pub fn stdin_answer() -> Option<String> {
    let mut line = String::new();
    match std::io::stdin().lock().read_line(&mut line) {
        Ok(0) | Err(_) => None,
        Ok(_) => Some(line),
    }
}

/// `~/.cx`, shared with the audit/undo records of `cx undo` / `cx audit`.
pub fn default_data_dir() -> Option<PathBuf> {
    dirs::home_dir().map(|h| h.join(".cx"))
}

#[derive(Serialize)]
struct AuditEntry<'a> {
    ts: String,
    event: &'a str,
    command: Option<String>,
    detail: serde_json::Value,
}

#[derive(Serialize)]
struct TransactionRecord {
    id: String,
    ts: String,
    command: String,
    undo: String,
    cwd: Option<String>,
    kind: &'static str,
    plan: Plan,
}

fn record(
    dir: Option<&Path>,
    event: &str,
    cmd: &PackageCommand,
    plan: &Plan,
    undo: Option<&str>,
) -> Result<()> {
    let dir = match dir {
        Some(d) => d,
        None => return Ok(()),
    };
    fs::create_dir_all(dir).with_context(|| format!("create {}", dir.display()))?;
    let ts = chrono::Utc::now().to_rfc3339();
    let command = cmd.argv.join(" ");
    append_line(
        &dir.join("audit.log"),
        &serde_json::to_string(&AuditEntry {
            ts: ts.clone(),
            event,
            command: Some(command.clone()),
            detail: serde_json::json!({ "source": "package_guard", "plan": plan }),
        })?,
    )?;
    if let Some(undo) = undo {
        append_line(
            &dir.join("transactions.jsonl"),
            &serde_json::to_string(&TransactionRecord {
                id: format!("tx-{}", chrono::Utc::now().timestamp_millis()),
                ts,
                command,
                undo: undo.to_string(),
                cwd: std::env::current_dir()
                    .ok()
                    .map(|p| p.to_string_lossy().into_owned()),
                kind: "package",
                plan: plan.clone(),
            })?,
        )?;
    }
    Ok(())
}

fn append_line(path: &Path, line: &str) -> Result<()> {
    let mut f = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .with_context(|| format!("open {}", path.display()))?;
    writeln!(f, "{}", line)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    // Real `LC_ALL=C apt-get -s install hello` output on Ubuntu 24.04 (2026-10-22).
    const SIM_INSTALL: &str = "Reading package lists...\nBuilding dependency tree...\nReading state information...\nThe following NEW packages will be installed:\n  hello\n0 upgraded, 1 newly installed, 0 to remove and 75 not upgraded.\nInst hello (2.10-3build1 Ubuntu:24.04/noble [amd64])\nConf hello (2.10-3build1 Ubuntu:24.04/noble [amd64])\n";

    struct FakeRunner {
        sim: SimOutput,
        executed: Vec<Vec<String>>,
        simulated: Vec<Vec<String>>,
    }

    impl FakeRunner {
        fn new(success: bool, stdout: &str, stderr: &str) -> Self {
            Self {
                sim: SimOutput {
                    success,
                    stdout: stdout.into(),
                    stderr: stderr.into(),
                },
                executed: vec![],
                simulated: vec![],
            }
        }
    }

    impl Runner for FakeRunner {
        fn simulate(&mut self, argv: &[String]) -> Result<SimOutput> {
            self.simulated.push(argv.to_vec());
            Ok(self.sim.clone())
        }
        fn execute(&mut self, argv: &[String]) -> Result<(bool, Option<i32>)> {
            self.executed.push(argv.to_vec());
            Ok((true, Some(0)))
        }
    }

    fn pkg(text: &str) -> PackageCommand {
        match classify(text) {
            Classification::Package(p) => p,
            other => panic!("{:?} classified as {:?}", text, other),
        }
    }

    fn run(
        text: &str,
        consent: Consent,
        runner: &mut FakeRunner,
        reply: Option<&str>,
        dir: Option<&Path>,
    ) -> (Outcome, String) {
        let reply = reply.map(str::to_string);
        let mut answer = move || reply.clone();
        let mut out = Vec::new();
        let outcome = guard(&pkg(text), consent, runner, &mut answer, &mut out, dir).unwrap();
        (outcome, String::from_utf8(out).unwrap())
    }

    #[test]
    fn classifies_package_changing_commands() {
        let p = pkg("sudo apt install -y nginx");
        assert_eq!(p.manager, Manager::Apt);
        assert_eq!(p.action, "install");
        assert_eq!(p.targets, vec!["nginx"]);
        assert_eq!(p.argv, vec!["sudo", "apt", "install", "-y", "nginx"]);
        assert_eq!(
            p.simulation.unwrap(),
            vec!["apt-get", "-s", "install", "nginx"]
        );
        assert_eq!(pkg("apt-get purge foo").action, "purge");
        assert_eq!(pkg("sudo apt full-upgrade").action, "dist-upgrade");
        assert_eq!(
            pkg("sudo apt-get install --no-install-recommends python3-pip")
                .simulation
                .unwrap(),
            vec![
                "apt-get",
                "-s",
                "--no-install-recommends",
                "install",
                "python3-pip"
            ]
        );
        assert_eq!(pkg("sudo dpkg -i ./cx.deb").manager, Manager::Dpkg);
        assert_eq!(
            pkg("sudo snap install code --classic").manager,
            Manager::Snap
        );
    }

    #[test]
    fn read_only_commands_are_not_package_changes() {
        for c in [
            "sudo apt update",
            "apt search nginx",
            "apt-cache search nginx",
            "apt list --installed",
            "apt-get -o Debug::X=1 update",
            "dpkg -l",
            "snap list",
            "man apt",
            "df -h",
        ] {
            assert_eq!(classify(c), Classification::NotPackage, "{}", c);
        }
    }

    #[test]
    fn hidden_or_unpreviewable_package_changes_are_refused() {
        for c in [
            "sudo apt install nginx; rm -rf /tmp/x",
            "curl x | sudo apt-get install -y nginx",
            "echo y | sudo apt install nginx",
            "sudo apt install $(cat pkgs)",
            "sudo apt install nginx > /dev/null",
            "sudo -E apt install nginx",
            "DEBIAN_FRONTEND=noninteractive apt-get install nginx",
            "sudo apt-get -o Dpkg::Options::=--force-all install nginx",
            "sudo apt-get -o Debug::X=1 install nginx",
            "sudo apt install",
            "sudo aptitude install nginx",
            "sudo apt install 'nginx; id'",
        ] {
            assert!(
                matches!(classify(c), Classification::Refused(_)),
                "{} was not refused: {:?}",
                c,
                classify(c)
            );
        }
    }

    #[test]
    fn and_chains_split_into_separately_guarded_commands() {
        assert_eq!(
            split_and_chain("sudo apt update && sudo apt install -y nginx"),
            vec!["sudo apt update", "sudo apt install -y nginx"]
        );
        // Other operators keep the text whole, so classify() refuses it.
        assert_eq!(
            split_and_chain("sudo apt update && sudo apt install nginx | tee log"),
            vec!["sudo apt update && sudo apt install nginx | tee log"]
        );
    }

    #[test]
    fn parses_real_simulation_output() {
        let plan = parse_simulation(SIM_INSTALL);
        assert_eq!(plan.install, vec!["hello"]);
        assert!(plan.upgrade.is_empty() && plan.remove.is_empty());
        let plan = parse_simulation(
            "Inst bash [5.2.21-2ubuntu4] (5.2.21-2ubuntu4.1 Ubuntu:24.04/noble-updates [amd64])\nRemv foo [1.0]\nPurg bar [2.0]\n",
        );
        assert_eq!(plan.upgrade, vec!["bash"]);
        assert_eq!(plan.remove, vec!["foo", "bar"]);
    }

    #[test]
    fn eof_never_executes() {
        let mut r = FakeRunner::new(true, SIM_INSTALL, "");
        let (outcome, text) = run(
            "sudo apt install hello",
            Consent::Prompt,
            &mut r,
            None,
            None,
        );
        assert_eq!(outcome, Outcome::Declined);
        assert!(r.executed.is_empty());
        assert_eq!(r.simulated.len(), 1);
        assert!(text.contains("Install (1): hello"));
        assert!(text.contains("No interactive input; not running."));
    }

    #[test]
    fn anything_but_yes_never_executes() {
        for reply in ["", "\n", "n", "no", "maybe", "yy"] {
            let mut r = FakeRunner::new(true, SIM_INSTALL, "");
            let (outcome, _) = run(
                "sudo apt install hello",
                Consent::Prompt,
                &mut r,
                Some(reply),
                None,
            );
            assert_eq!(outcome, Outcome::Declined, "reply {:?}", reply);
            assert!(r.executed.is_empty(), "reply {:?} executed", reply);
        }
    }

    #[test]
    fn yes_executes_the_exact_argv_after_preview() {
        let mut r = FakeRunner::new(true, SIM_INSTALL, "");
        let (outcome, text) = run(
            "sudo apt install hello",
            Consent::Prompt,
            &mut r,
            Some("y\n"),
            None,
        );
        assert_eq!(
            outcome,
            Outcome::Executed {
                success: true,
                code: Some(0)
            }
        );
        assert_eq!(r.executed, vec![vec!["sudo", "apt", "install", "hello"]]);
        let preview_at = text.find("Install (1): hello").unwrap();
        let prompt_at = text.find("[y/N]").unwrap();
        assert!(
            preview_at < prompt_at,
            "preview must come before the prompt"
        );
    }

    #[test]
    fn failed_preview_never_executes_even_with_explicit_consent() {
        let mut r = FakeRunner::new(false, "", "E: Unable to locate package nosuchpkg\n");
        let (outcome, text) = run(
            "sudo apt install nosuchpkg",
            Consent::Explicit,
            &mut r,
            None,
            None,
        );
        assert_eq!(
            outcome,
            Outcome::PreviewFailed("E: Unable to locate package nosuchpkg".into())
        );
        assert!(r.executed.is_empty());
        assert!(text.contains("nothing was run"));
    }

    #[test]
    fn nothing_to_do_never_executes() {
        let mut r = FakeRunner::new(true, "0 upgraded, 0 newly installed, 0 to remove.\n", "");
        let (outcome, _) = run(
            "sudo apt install hello",
            Consent::Explicit,
            &mut r,
            None,
            None,
        );
        assert_eq!(outcome, Outcome::NothingToDo);
        assert!(r.executed.is_empty());
    }

    #[test]
    fn explicit_consent_still_shows_preview() {
        let mut r = FakeRunner::new(true, SIM_INSTALL, "");
        let (outcome, text) = run(
            "sudo apt install -y hello",
            Consent::Explicit,
            &mut r,
            None,
            None,
        );
        assert!(matches!(outcome, Outcome::Executed { success: true, .. }));
        assert!(text.contains("Install (1): hello"));
        assert!(!text.contains("[y/N]"));
    }

    #[test]
    fn unsimulated_managers_still_require_consent() {
        let mut r = FakeRunner::new(true, "", "");
        let (outcome, text) = run(
            "sudo snap install code --classic",
            Consent::Prompt,
            &mut r,
            None,
            None,
        );
        assert_eq!(outcome, Outcome::Declined);
        assert!(r.simulated.is_empty() && r.executed.is_empty());
        assert!(text.contains("has no dry-run mode"));
    }

    #[test]
    fn records_audit_and_reversible_transaction() {
        let dir = tempfile::tempdir().unwrap();
        let mut r = FakeRunner::new(true, SIM_INSTALL, "");
        let (_, text) = run(
            "sudo apt install hello",
            Consent::Prompt,
            &mut r,
            Some("y"),
            Some(dir.path()),
        );
        assert!(text.contains("To reverse: sudo apt-get remove hello"));
        let audit = fs::read_to_string(dir.path().join("audit.log")).unwrap();
        assert!(audit.contains("\"event\":\"package_executed\""));
        let tx = fs::read_to_string(dir.path().join("transactions.jsonl")).unwrap();
        let v: serde_json::Value = serde_json::from_str(tx.lines().next().unwrap()).unwrap();
        assert_eq!(v["command"], "sudo apt install hello");
        assert_eq!(v["undo"], "sudo apt-get remove hello");
        assert_eq!(v["kind"], "package");
        assert!(v["id"].as_str().unwrap().starts_with("tx-"));
    }

    #[test]
    fn declines_are_audited_but_not_transactions() {
        let dir = tempfile::tempdir().unwrap();
        let mut r = FakeRunner::new(true, SIM_INSTALL, "");
        run(
            "sudo apt install hello",
            Consent::Prompt,
            &mut r,
            Some("n"),
            Some(dir.path()),
        );
        let audit = fs::read_to_string(dir.path().join("audit.log")).unwrap();
        assert!(audit.contains("package_declined"));
        assert!(!dir.path().join("transactions.jsonl").exists());
    }

    /// Real apt, real processes. `apt-get -s` is always safe; the install/undo half
    /// runs only with CX_GUARD_E2E=1 (use a throwaway container, as root):
    /// `CX_GUARD_E2E=1 cargo test -p cx-terminal real_apt -- --ignored`
    #[test]
    #[ignore]
    fn real_apt_preview_execute_and_undo() {
        let mut runner = SystemRunner;
        let mut out = Vec::new();
        let mut no = || None;
        let cmd = pkg("apt-get install -y hello");
        let outcome = guard(&cmd, Consent::Prompt, &mut runner, &mut no, &mut out, None).unwrap();
        let text = String::from_utf8_lossy(&out).into_owned();
        println!("{}", text);
        if text.contains("Nothing to change") {
            assert_eq!(outcome, Outcome::NothingToDo);
        } else {
            assert_eq!(outcome, Outcome::Declined);
            assert!(text.contains("Install (1): hello"), "{}", text);
        }

        if std::env::var("CX_GUARD_E2E").as_deref() != Ok("1") {
            return;
        }
        let dir = tempfile::tempdir().unwrap();
        let mut yes = || Some("y".to_string());
        let mut out = Vec::new();
        let outcome = guard(
            &cmd,
            Consent::Prompt,
            &mut runner,
            &mut yes,
            &mut out,
            Some(dir.path()),
        )
        .unwrap();
        println!("{}", String::from_utf8_lossy(&out));
        assert_eq!(
            outcome,
            Outcome::Executed {
                success: true,
                code: Some(0)
            }
        );
        assert!(Path::new("/usr/bin/hello").exists());

        let tx = fs::read_to_string(dir.path().join("transactions.jsonl")).unwrap();
        let v: serde_json::Value = serde_json::from_str(tx.lines().next().unwrap()).unwrap();
        assert_eq!(v["undo"], "sudo apt-get remove hello");
        let undo = pkg("apt-get remove -y hello");
        let mut out = Vec::new();
        let outcome = guard(
            &undo,
            Consent::Explicit,
            &mut runner,
            &mut yes,
            &mut out,
            Some(dir.path()),
        )
        .unwrap();
        println!("{}", String::from_utf8_lossy(&out));
        assert_eq!(
            outcome,
            Outcome::Executed {
                success: true,
                code: Some(0)
            }
        );
        assert!(!Path::new("/usr/bin/hello").exists());
    }

    #[test]
    fn undo_only_for_pure_installs_or_removals() {
        let p = |i: &[&str], u: &[&str], r: &[&str]| Plan {
            install: i.iter().map(|s| s.to_string()).collect(),
            upgrade: u.iter().map(|s| s.to_string()).collect(),
            remove: r.iter().map(|s| s.to_string()).collect(),
            simulated: true,
        };
        assert_eq!(
            p(&["a", "b"], &[], &[]).undo_command().as_deref(),
            Some("sudo apt-get remove a b")
        );
        assert_eq!(
            p(&[], &[], &["c"]).undo_command().as_deref(),
            Some("sudo apt-get install c")
        );
        assert_eq!(p(&["a"], &["b"], &[]).undo_command(), None);
        assert_eq!(p(&["a"], &[], &["c"]).undo_command(), None);
    }
}
