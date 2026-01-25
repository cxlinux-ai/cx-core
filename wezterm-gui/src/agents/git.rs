//! Git Agent - Git repository operations
//!
//! Provides capabilities for:
//! - Git status
//! - Git diff
//! - Git log
//! - Staging files
//! - Committing (with AI-generated message)
//! - Push/pull operations

use super::traits::{Agent, AgentCapability, AgentRequest, AgentResponse};
use std::process::Command;

/// Commands that the git agent can handle
#[derive(Debug, Clone, PartialEq)]
pub enum GitCommand {
    /// Show git status
    Status,
    /// Show diff
    Diff { staged: bool, file: Option<String> },
    /// Show log
    Log { count: usize, oneline: bool },
    /// List branches
    Branches { all: bool },
    /// Current branch
    CurrentBranch,
    /// Stage files
    Stage { files: Vec<String> },
    /// Unstage files
    Unstage { files: Vec<String> },
    /// Commit with message
    Commit { message: String },
    /// Push to remote
    Push { remote: Option<String>, branch: Option<String> },
    /// Pull from remote
    Pull { remote: Option<String>, branch: Option<String> },
    /// Fetch from remote
    Fetch { remote: Option<String> },
    /// Create branch
    CreateBranch { name: String },
    /// Switch branch
    SwitchBranch { name: String },
    /// Delete branch
    DeleteBranch { name: String },
    /// Stash changes
    Stash { pop: bool },
    /// Show remote
    Remote,
    /// Show blame for file
    Blame { file: String },
    /// Unknown command
    Unknown(String),
}

impl GitCommand {
    /// Parse a command string into a GitCommand
    pub fn parse(input: &str) -> Self {
        let input_lower = input.to_lowercase();
        let words: Vec<&str> = input.split_whitespace().collect();

        // Status
        if input_lower.contains("status") || input_lower == "st" {
            return Self::Status;
        }

        // Diff
        if input_lower.contains("diff") {
            let staged = input_lower.contains("staged") || input_lower.contains("--cached");
            let file = words.iter()
                .find(|w| w.contains('.') || w.contains('/'))
                .map(|s| s.to_string());
            return Self::Diff { staged, file };
        }

        // Log
        if input_lower.contains("log") || input_lower.contains("history")
            || input_lower.contains("commits")
        {
            let count = words.iter()
                .filter_map(|w| w.parse::<usize>().ok())
                .next()
                .unwrap_or(10);
            let oneline = input_lower.contains("oneline") || input_lower.contains("short");
            return Self::Log { count, oneline };
        }

        // Branches
        if input_lower.contains("branch") {
            if input_lower.contains("create") || input_lower.contains("new") {
                if let Some(name) = words.last() {
                    return Self::CreateBranch { name: name.to_string() };
                }
            }
            if input_lower.contains("delete") || input_lower.contains("remove") {
                if let Some(name) = words.last() {
                    return Self::DeleteBranch { name: name.to_string() };
                }
            }
            if input_lower.contains("switch") || input_lower.contains("checkout") {
                if let Some(name) = words.last() {
                    return Self::SwitchBranch { name: name.to_string() };
                }
            }
            if input_lower.contains("current") {
                return Self::CurrentBranch;
            }
            let all = input_lower.contains("all") || input_lower.contains("-a");
            return Self::Branches { all };
        }

        // Switch/checkout
        if input_lower.contains("switch") || input_lower.contains("checkout") {
            if let Some(name) = words.last() {
                return Self::SwitchBranch { name: name.to_string() };
            }
        }

        // Stage (add)
        if input_lower.contains("stage") || input_lower.starts_with("add ")
            || input_lower.contains("git add")
        {
            let files: Vec<String> = words.iter()
                .skip_while(|&w| w.to_lowercase() != "stage" && w.to_lowercase() != "add")
                .skip(1)
                .map(|s| s.to_string())
                .collect();

            if files.is_empty() {
                return Self::Stage { files: vec![".".to_string()] };
            }
            return Self::Stage { files };
        }

        // Unstage
        if input_lower.contains("unstage") || input_lower.contains("reset head") {
            let files: Vec<String> = words.iter()
                .skip_while(|&w| w.to_lowercase() != "unstage")
                .skip(1)
                .map(|s| s.to_string())
                .collect();
            return Self::Unstage { files };
        }

        // Commit
        if input_lower.contains("commit") {
            // Look for message in quotes
            let message = Self::extract_quoted(input)
                .or_else(|| {
                    // Look for message after -m
                    if let Some(idx) = words.iter().position(|&w| w == "-m") {
                        words.get(idx + 1).map(|s| s.to_string())
                    } else {
                        None
                    }
                })
                .unwrap_or_else(|| "Update".to_string());
            return Self::Commit { message };
        }

        // Push
        if input_lower.contains("push") {
            let (remote, branch) = Self::extract_remote_branch(&words, "push");
            return Self::Push { remote, branch };
        }

        // Pull
        if input_lower.contains("pull") {
            let (remote, branch) = Self::extract_remote_branch(&words, "pull");
            return Self::Pull { remote, branch };
        }

        // Fetch
        if input_lower.contains("fetch") {
            let remote = words.iter()
                .skip_while(|&w| w.to_lowercase() != "fetch")
                .nth(1)
                .map(|s| s.to_string());
            return Self::Fetch { remote };
        }

        // Stash
        if input_lower.contains("stash") {
            let pop = input_lower.contains("pop") || input_lower.contains("apply");
            return Self::Stash { pop };
        }

        // Remote
        if input_lower.contains("remote") {
            return Self::Remote;
        }

        // Blame
        if input_lower.contains("blame") {
            if let Some(file) = words.last() {
                return Self::Blame { file: file.to_string() };
            }
        }

        Self::Unknown(input.to_string())
    }

    /// Extract a quoted string from input
    fn extract_quoted(input: &str) -> Option<String> {
        // Look for double-quoted string
        if let Some(start) = input.find('"') {
            if let Some(end) = input[start + 1..].find('"') {
                return Some(input[start + 1..start + 1 + end].to_string());
            }
        }
        // Look for single-quoted string
        if let Some(start) = input.find('\'') {
            if let Some(end) = input[start + 1..].find('\'') {
                return Some(input[start + 1..start + 1 + end].to_string());
            }
        }
        None
    }

    /// Extract remote and branch from words
    fn extract_remote_branch(words: &[&str], keyword: &str) -> (Option<String>, Option<String>) {
        let after_keyword: Vec<_> = words.iter()
            .skip_while(|&w| w.to_lowercase() != keyword)
            .skip(1)
            .collect();

        match after_keyword.len() {
            0 => (None, None),
            1 => (Some(after_keyword[0].to_string()), None),
            _ => (Some(after_keyword[0].to_string()), Some(after_keyword[1].to_string())),
        }
    }
}

/// Git agent for repository operations
pub struct GitAgent {
    capabilities: Vec<AgentCapability>,
}

impl GitAgent {
    /// Create a new git agent
    pub fn new() -> Self {
        Self {
            capabilities: vec![
                AgentCapability::Execute,
                AgentCapability::Custom("git".to_string()),
            ],
        }
    }

    /// Execute a git command and return output
    fn execute_git(&self, args: &[&str]) -> Result<String, String> {
        match Command::new("git").args(args).output() {
            Ok(output) => {
                if output.status.success() {
                    Ok(String::from_utf8_lossy(&output.stdout).to_string())
                } else {
                    let stderr = String::from_utf8_lossy(&output.stderr);
                    if stderr.is_empty() {
                        Err(format!("Git command failed with exit code: {:?}", output.status.code()))
                    } else {
                        Err(stderr.to_string())
                    }
                }
            }
            Err(e) => Err(format!("Failed to execute git: {}", e)),
        }
    }

    /// Check if we're in a git repository
    fn is_git_repo(&self) -> bool {
        self.execute_git(&["rev-parse", "--is-inside-work-tree"]).is_ok()
    }

    /// Get git status
    fn status(&self) -> AgentResponse {
        if !self.is_git_repo() {
            return AgentResponse::error("Not a git repository".to_string());
        }

        match self.execute_git(&["status"]) {
            Ok(output) => AgentResponse::success(output)
                .with_commands(vec!["git status".to_string()])
                .with_suggestions(vec![
                    "show diff".to_string(),
                    "stage all".to_string(),
                    "show log".to_string(),
                ]),
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Get git diff
    fn diff(&self, staged: bool, file: Option<&str>) -> AgentResponse {
        if !self.is_git_repo() {
            return AgentResponse::error("Not a git repository".to_string());
        }

        let mut args = vec!["diff"];
        if staged {
            args.push("--cached");
        }
        if let Some(f) = file {
            args.push(f);
        }

        match self.execute_git(&args) {
            Ok(output) => {
                let cmd = format!("git {}", args.join(" "));
                let result = if output.trim().is_empty() {
                    "No changes".to_string()
                } else {
                    output
                };
                AgentResponse::success(result)
                    .with_commands(vec![cmd])
                    .with_suggestions(vec![
                        "stage all".to_string(),
                        "commit".to_string(),
                    ])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Get git log
    fn log(&self, count: usize, oneline: bool) -> AgentResponse {
        if !self.is_git_repo() {
            return AgentResponse::error("Not a git repository".to_string());
        }

        let count_str = count.to_string();
        let mut args = vec!["log", "-n", &count_str];
        if oneline {
            args.push("--oneline");
        } else {
            args.extend(&["--format=%h %s (%an, %ar)"]);
        }

        match self.execute_git(&args) {
            Ok(output) => {
                let cmd = format!("git {}", args.join(" "));
                AgentResponse::success(output)
                    .with_commands(vec![cmd])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// List branches
    fn branches(&self, all: bool) -> AgentResponse {
        if !self.is_git_repo() {
            return AgentResponse::error("Not a git repository".to_string());
        }

        let mut args = vec!["branch"];
        if all {
            args.push("-a");
        }

        match self.execute_git(&args) {
            Ok(output) => {
                let cmd = format!("git {}", args.join(" "));
                AgentResponse::success(output)
                    .with_commands(vec![cmd])
                    .with_suggestions(vec![
                        "create branch feature/new".to_string(),
                        "switch to main".to_string(),
                    ])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Get current branch
    fn current_branch(&self) -> AgentResponse {
        if !self.is_git_repo() {
            return AgentResponse::error("Not a git repository".to_string());
        }

        match self.execute_git(&["rev-parse", "--abbrev-ref", "HEAD"]) {
            Ok(output) => AgentResponse::success(output.trim().to_string())
                .with_commands(vec!["git rev-parse --abbrev-ref HEAD".to_string()]),
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Stage files
    fn stage(&self, files: &[String]) -> AgentResponse {
        if !self.is_git_repo() {
            return AgentResponse::error("Not a git repository".to_string());
        }

        let mut args = vec!["add"];
        let file_refs: Vec<&str> = files.iter().map(|s| s.as_str()).collect();
        args.extend(file_refs);

        match self.execute_git(&args) {
            Ok(_) => {
                let cmd = format!("git add {}", files.join(" "));
                AgentResponse::success(format!("Staged: {}", files.join(", ")))
                    .with_commands(vec![cmd])
                    .with_suggestions(vec![
                        "show staged diff".to_string(),
                        "commit".to_string(),
                    ])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Unstage files
    fn unstage(&self, files: &[String]) -> AgentResponse {
        if !self.is_git_repo() {
            return AgentResponse::error("Not a git repository".to_string());
        }

        let mut args = vec!["reset", "HEAD"];
        let file_refs: Vec<&str> = files.iter().map(|s| s.as_str()).collect();
        if !files.is_empty() {
            args.extend(file_refs);
        }

        match self.execute_git(&args) {
            Ok(_) => {
                let cmd = format!("git reset HEAD {}", files.join(" "));
                AgentResponse::success("Files unstaged".to_string())
                    .with_commands(vec![cmd])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Commit with message
    fn commit(&self, message: &str) -> AgentResponse {
        if !self.is_git_repo() {
            return AgentResponse::error("Not a git repository".to_string());
        }

        // For safety, we return the command to execute
        let cmd = format!("git commit -m \"{}\"", message.replace('"', "\\\""));

        AgentResponse::success(format!(
            "To commit, run:\n\n  {}\n\nThis requires confirmation before execution.",
            cmd
        ))
        .with_commands(vec![cmd])
        .with_suggestions(vec![
            "push".to_string(),
            "show log".to_string(),
        ])
    }

    /// Push to remote
    fn push(&self, remote: Option<&str>, branch: Option<&str>) -> AgentResponse {
        if !self.is_git_repo() {
            return AgentResponse::error("Not a git repository".to_string());
        }

        let remote = remote.unwrap_or("origin");
        let branch = branch.unwrap_or_else(|| {
            // Get current branch
            "HEAD"
        });

        let cmd = format!("git push {} {}", remote, branch);

        AgentResponse::success(format!(
            "To push, run:\n\n  {}\n\nThis requires confirmation before execution.",
            cmd
        ))
        .with_commands(vec![cmd])
    }

    /// Pull from remote
    fn pull(&self, remote: Option<&str>, branch: Option<&str>) -> AgentResponse {
        if !self.is_git_repo() {
            return AgentResponse::error("Not a git repository".to_string());
        }

        let remote = remote.unwrap_or("origin");
        let mut args = vec!["pull", remote];
        if let Some(b) = branch {
            args.push(b);
        }

        match self.execute_git(&args) {
            Ok(output) => {
                let cmd = format!("git {}", args.join(" "));
                AgentResponse::success(output)
                    .with_commands(vec![cmd])
                    .with_suggestions(vec![
                        "show status".to_string(),
                        "show log".to_string(),
                    ])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Fetch from remote
    fn fetch(&self, remote: Option<&str>) -> AgentResponse {
        if !self.is_git_repo() {
            return AgentResponse::error("Not a git repository".to_string());
        }

        let remote = remote.unwrap_or("origin");

        match self.execute_git(&["fetch", remote]) {
            Ok(output) => {
                let result = if output.trim().is_empty() {
                    "Fetched successfully (no new changes)".to_string()
                } else {
                    output
                };
                AgentResponse::success(result)
                    .with_commands(vec![format!("git fetch {}", remote)])
                    .with_suggestions(vec![
                        "show status".to_string(),
                        "pull".to_string(),
                    ])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Create branch
    fn create_branch(&self, name: &str) -> AgentResponse {
        if !self.is_git_repo() {
            return AgentResponse::error("Not a git repository".to_string());
        }

        match self.execute_git(&["checkout", "-b", name]) {
            Ok(_) => {
                AgentResponse::success(format!("Created and switched to branch: {}", name))
                    .with_commands(vec![format!("git checkout -b {}", name)])
                    .with_suggestions(vec![
                        "show status".to_string(),
                        "list branches".to_string(),
                    ])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Switch branch
    fn switch_branch(&self, name: &str) -> AgentResponse {
        if !self.is_git_repo() {
            return AgentResponse::error("Not a git repository".to_string());
        }

        match self.execute_git(&["checkout", name]) {
            Ok(_) => {
                AgentResponse::success(format!("Switched to branch: {}", name))
                    .with_commands(vec![format!("git checkout {}", name)])
                    .with_suggestions(vec![
                        "show status".to_string(),
                        "show log".to_string(),
                    ])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Delete branch
    fn delete_branch(&self, name: &str) -> AgentResponse {
        if !self.is_git_repo() {
            return AgentResponse::error("Not a git repository".to_string());
        }

        let cmd = format!("git branch -d {}", name);

        AgentResponse::success(format!(
            "To delete branch '{}', run:\n\n  {}\n\nThis requires confirmation before execution.",
            name, cmd
        ))
        .with_commands(vec![cmd])
    }

    /// Stash changes
    fn stash(&self, pop: bool) -> AgentResponse {
        if !self.is_git_repo() {
            return AgentResponse::error("Not a git repository".to_string());
        }

        let args = if pop { vec!["stash", "pop"] } else { vec!["stash"] };

        match self.execute_git(&args) {
            Ok(output) => {
                let result = if output.trim().is_empty() {
                    if pop {
                        "Applied stashed changes".to_string()
                    } else {
                        "Changes stashed".to_string()
                    }
                } else {
                    output
                };
                AgentResponse::success(result)
                    .with_commands(vec![format!("git {}", args.join(" "))])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Show remotes
    fn remote(&self) -> AgentResponse {
        if !self.is_git_repo() {
            return AgentResponse::error("Not a git repository".to_string());
        }

        match self.execute_git(&["remote", "-v"]) {
            Ok(output) => {
                let result = if output.trim().is_empty() {
                    "No remotes configured".to_string()
                } else {
                    output
                };
                AgentResponse::success(result)
                    .with_commands(vec!["git remote -v".to_string()])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Show blame for file
    fn blame(&self, file: &str) -> AgentResponse {
        if !self.is_git_repo() {
            return AgentResponse::error("Not a git repository".to_string());
        }

        match self.execute_git(&["blame", file]) {
            Ok(output) => {
                AgentResponse::success(output)
                    .with_commands(vec![format!("git blame {}", file)])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Handle unknown command
    fn handle_unknown(&self, command: &str) -> AgentResponse {
        AgentResponse::error(format!("Unknown git command: {}", command))
            .with_suggestions(vec![
                "show status".to_string(),
                "show diff".to_string(),
                "show log".to_string(),
                "list branches".to_string(),
            ])
    }
}

impl Default for GitAgent {
    fn default() -> Self {
        Self::new()
    }
}

impl Agent for GitAgent {
    fn name(&self) -> &str {
        "git"
    }

    fn description(&self) -> &str {
        "Git repository operations"
    }

    fn capabilities(&self) -> &[AgentCapability] {
        &self.capabilities
    }

    fn can_handle(&self, request: &AgentRequest) -> bool {
        // Handle if explicitly targeted at git agent
        if request.agent == "git" {
            return true;
        }

        // Check if the command matches git-related keywords
        let cmd_lower = request.command.to_lowercase();
        cmd_lower.contains("git")
            || cmd_lower.contains("commit")
            || cmd_lower.contains("branch")
            || cmd_lower.contains("merge")
            || cmd_lower.contains("push")
            || cmd_lower.contains("pull")
            || cmd_lower.contains("checkout")
            || cmd_lower.contains("stash")
    }

    fn handle(&self, request: AgentRequest) -> AgentResponse {
        let command = GitCommand::parse(&request.command);

        match command {
            GitCommand::Status => self.status(),
            GitCommand::Diff { staged, file } => self.diff(staged, file.as_deref()),
            GitCommand::Log { count, oneline } => self.log(count, oneline),
            GitCommand::Branches { all } => self.branches(all),
            GitCommand::CurrentBranch => self.current_branch(),
            GitCommand::Stage { files } => self.stage(&files),
            GitCommand::Unstage { files } => self.unstage(&files),
            GitCommand::Commit { message } => self.commit(&message),
            GitCommand::Push { remote, branch } => self.push(remote.as_deref(), branch.as_deref()),
            GitCommand::Pull { remote, branch } => self.pull(remote.as_deref(), branch.as_deref()),
            GitCommand::Fetch { remote } => self.fetch(remote.as_deref()),
            GitCommand::CreateBranch { name } => self.create_branch(&name),
            GitCommand::SwitchBranch { name } => self.switch_branch(&name),
            GitCommand::DeleteBranch { name } => self.delete_branch(&name),
            GitCommand::Stash { pop } => self.stash(pop),
            GitCommand::Remote => self.remote(),
            GitCommand::Blame { file } => self.blame(&file),
            GitCommand::Unknown(cmd) => self.handle_unknown(&cmd),
        }
    }

    fn examples(&self) -> &[&str] {
        &[
            "show status",
            "show diff",
            "show staged diff",
            "show last 10 commits",
            "list branches",
            "create branch feature/new",
            "stage all",
            "commit \"fix: update readme\"",
            "push origin main",
            "pull",
            "stash",
            "stash pop",
        ]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_status() {
        assert_eq!(GitCommand::parse("show status"), GitCommand::Status);
        assert_eq!(GitCommand::parse("status"), GitCommand::Status);
    }

    #[test]
    fn test_parse_diff() {
        assert!(matches!(
            GitCommand::parse("show diff"),
            GitCommand::Diff { staged: false, file: None }
        ));
        assert!(matches!(
            GitCommand::parse("show staged diff"),
            GitCommand::Diff { staged: true, file: None }
        ));
    }

    #[test]
    fn test_parse_log() {
        assert!(matches!(
            GitCommand::parse("show last 5 commits"),
            GitCommand::Log { count: 5, oneline: false }
        ));
    }

    #[test]
    fn test_parse_commit() {
        assert!(matches!(
            GitCommand::parse("commit \"fix: bug\""),
            GitCommand::Commit { message } if message == "fix: bug"
        ));
    }

    #[test]
    fn test_agent_can_handle() {
        let agent = GitAgent::new();

        let req = AgentRequest::new("git", "show status");
        assert!(agent.can_handle(&req));

        let req = AgentRequest::new("other", "commit changes");
        assert!(agent.can_handle(&req));
    }
}
