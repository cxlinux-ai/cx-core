//! Package Agent - Package management
//!
//! Provides capabilities for:
//! - Searching packages (apt search, pacman -Ss, brew search)
//! - Installing packages (with confirmation)
//! - Listing installed packages
//! - Checking for updates
//! - Detecting package manager (apt, pacman, dnf, brew)

use super::traits::{Agent, AgentCapability, AgentRequest, AgentResponse};
use std::process::Command;

/// Detected package manager
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PackageManager {
    Apt,
    Pacman,
    Dnf,
    Yum,
    Zypper,
    Brew,
    Nix,
    Unknown,
}

impl PackageManager {
    /// Detect the system's package manager
    pub fn detect() -> Self {
        // Check for common package managers
        if Self::command_exists("apt") {
            Self::Apt
        } else if Self::command_exists("pacman") {
            Self::Pacman
        } else if Self::command_exists("dnf") {
            Self::Dnf
        } else if Self::command_exists("yum") {
            Self::Yum
        } else if Self::command_exists("zypper") {
            Self::Zypper
        } else if Self::command_exists("brew") {
            Self::Brew
        } else if Self::command_exists("nix-env") {
            Self::Nix
        } else {
            Self::Unknown
        }
    }

    fn command_exists(cmd: &str) -> bool {
        Command::new("which")
            .arg(cmd)
            .output()
            .map(|o| o.status.success())
            .unwrap_or(false)
    }

    /// Get the name of the package manager
    pub fn name(&self) -> &'static str {
        match self {
            Self::Apt => "apt",
            Self::Pacman => "pacman",
            Self::Dnf => "dnf",
            Self::Yum => "yum",
            Self::Zypper => "zypper",
            Self::Brew => "brew",
            Self::Nix => "nix",
            Self::Unknown => "unknown",
        }
    }
}

/// Commands that the package agent can handle
#[derive(Debug, Clone, PartialEq)]
pub enum PackageCommand {
    /// Search for packages
    Search { query: String },
    /// Install a package
    Install { package: String },
    /// Remove a package
    Remove { package: String },
    /// List installed packages
    ListInstalled { filter: Option<String> },
    /// Check for updates
    CheckUpdates,
    /// Upgrade all packages
    Upgrade,
    /// Show package info
    Info { package: String },
    /// List package files
    ListFiles { package: String },
    /// Which package owns a file
    WhoOwns { file: String },
    /// Clean package cache
    Clean,
    /// Unknown command
    Unknown(String),
}

impl PackageCommand {
    /// Parse a command string into a PackageCommand
    pub fn parse(input: &str) -> Self {
        let input_lower = input.to_lowercase();
        let words: Vec<&str> = input.split_whitespace().collect();

        // Search
        if input_lower.contains("search") || input_lower.contains("find package") {
            let query = words.iter()
                .skip_while(|&w| w.to_lowercase() != "search" && w.to_lowercase() != "for")
                .nth(1)
                .map(|s| s.to_string())
                .or_else(|| words.last().map(|s| s.to_string()))
                .unwrap_or_default();
            return Self::Search { query };
        }

        // Install
        if input_lower.contains("install") {
            let package = words.iter()
                .skip_while(|&w| w.to_lowercase() != "install")
                .nth(1)
                .map(|s| s.to_string())
                .or_else(|| words.last().map(|s| s.to_string()))
                .unwrap_or_default();
            return Self::Install { package };
        }

        // Remove/uninstall
        if input_lower.contains("remove") || input_lower.contains("uninstall") {
            let package = words.iter()
                .skip_while(|&w| w.to_lowercase() != "remove" && w.to_lowercase() != "uninstall")
                .nth(1)
                .map(|s| s.to_string())
                .or_else(|| words.last().map(|s| s.to_string()))
                .unwrap_or_default();
            return Self::Remove { package };
        }

        // List installed
        if input_lower.contains("list") && input_lower.contains("install") {
            let filter = words.iter()
                .skip_while(|&w| w.to_lowercase() != "installed")
                .nth(1)
                .map(|s| s.to_string());
            return Self::ListInstalled { filter };
        }

        // Check updates
        if input_lower.contains("update") || input_lower.contains("check") {
            if input_lower.contains("upgrade") || input_lower.contains("all") {
                return Self::Upgrade;
            }
            return Self::CheckUpdates;
        }

        // Upgrade
        if input_lower.contains("upgrade") {
            return Self::Upgrade;
        }

        // Package info
        if input_lower.contains("info") || input_lower.contains("details")
            || input_lower.contains("about")
        {
            let package = words.iter()
                .skip_while(|&w| w.to_lowercase() != "info" && w.to_lowercase() != "about")
                .nth(1)
                .map(|s| s.to_string())
                .or_else(|| words.last().map(|s| s.to_string()))
                .unwrap_or_default();
            return Self::Info { package };
        }

        // List files
        if input_lower.contains("files") && input_lower.contains("list") {
            let package = words.last().map(|s| s.to_string()).unwrap_or_default();
            return Self::ListFiles { package };
        }

        // Who owns
        if input_lower.contains("owns") || input_lower.contains("which package") {
            let file = words.iter()
                .skip_while(|&w| w.to_lowercase() != "owns" && w.to_lowercase() != "package")
                .nth(1)
                .map(|s| s.to_string())
                .or_else(|| words.last().map(|s| s.to_string()))
                .unwrap_or_default();
            return Self::WhoOwns { file };
        }

        // Clean
        if input_lower.contains("clean") || input_lower.contains("clear cache") {
            return Self::Clean;
        }

        Self::Unknown(input.to_string())
    }
}

/// Package agent for package management
pub struct PackageAgent {
    capabilities: Vec<AgentCapability>,
    package_manager: PackageManager,
}

impl PackageAgent {
    /// Create a new package agent
    pub fn new() -> Self {
        Self {
            capabilities: vec![
                AgentCapability::PackageManage,
                AgentCapability::Execute,
            ],
            package_manager: PackageManager::detect(),
        }
    }

    /// Execute a shell command and return output
    fn execute_command(&self, cmd: &str, args: &[&str]) -> Result<String, String> {
        match Command::new(cmd).args(args).output() {
            Ok(output) => {
                if output.status.success() {
                    Ok(String::from_utf8_lossy(&output.stdout).to_string())
                } else {
                    let stderr = String::from_utf8_lossy(&output.stderr);
                    if stderr.is_empty() {
                        Err(format!("Command failed with exit code: {:?}", output.status.code()))
                    } else {
                        Err(stderr.to_string())
                    }
                }
            }
            Err(e) => Err(format!("Failed to execute {}: {}", cmd, e)),
        }
    }

    /// Search for packages
    fn search_packages(&self, query: &str) -> AgentResponse {
        let (cmd, args): (&str, Vec<&str>) = match self.package_manager {
            PackageManager::Apt => ("apt", vec!["search", query]),
            PackageManager::Pacman => ("pacman", vec!["-Ss", query]),
            PackageManager::Dnf => ("dnf", vec!["search", query]),
            PackageManager::Yum => ("yum", vec!["search", query]),
            PackageManager::Zypper => ("zypper", vec!["search", query]),
            PackageManager::Brew => ("brew", vec!["search", query]),
            PackageManager::Nix => ("nix-env", vec!["-qaP", query]),
            PackageManager::Unknown => {
                return AgentResponse::error("No package manager detected".to_string());
            }
        };

        match self.execute_command(cmd, &args) {
            Ok(output) => {
                let cmd_str = format!("{} {}", cmd, args.join(" "));
                AgentResponse::success(output)
                    .with_commands(vec![cmd_str])
                    .with_suggestions(vec![
                        format!("install {}", query),
                        format!("info {}", query),
                    ])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Install a package (returns command to run, requires confirmation)
    fn install_package(&self, package: &str) -> AgentResponse {
        let cmd_str = match self.package_manager {
            PackageManager::Apt => format!("sudo apt install -y {}", package),
            PackageManager::Pacman => format!("sudo pacman -S {}", package),
            PackageManager::Dnf => format!("sudo dnf install -y {}", package),
            PackageManager::Yum => format!("sudo yum install -y {}", package),
            PackageManager::Zypper => format!("sudo zypper install -y {}", package),
            PackageManager::Brew => format!("brew install {}", package),
            PackageManager::Nix => format!("nix-env -iA nixpkgs.{}", package),
            PackageManager::Unknown => {
                return AgentResponse::error("No package manager detected".to_string());
            }
        };

        // Return the command to execute - requires user confirmation
        AgentResponse::success(format!(
            "To install '{}', run:\n\n  {}\n\nThis requires confirmation before execution.",
            package, cmd_str
        ))
        .with_commands(vec![cmd_str])
        .with_suggestions(vec![
            format!("search {}", package),
            format!("info {}", package),
        ])
    }

    /// Remove a package (returns command to run, requires confirmation)
    fn remove_package(&self, package: &str) -> AgentResponse {
        let cmd_str = match self.package_manager {
            PackageManager::Apt => format!("sudo apt remove {}", package),
            PackageManager::Pacman => format!("sudo pacman -Rs {}", package),
            PackageManager::Dnf => format!("sudo dnf remove {}", package),
            PackageManager::Yum => format!("sudo yum remove {}", package),
            PackageManager::Zypper => format!("sudo zypper remove {}", package),
            PackageManager::Brew => format!("brew uninstall {}", package),
            PackageManager::Nix => format!("nix-env -e {}", package),
            PackageManager::Unknown => {
                return AgentResponse::error("No package manager detected".to_string());
            }
        };

        // Return the command to execute - requires user confirmation
        AgentResponse::success(format!(
            "To remove '{}', run:\n\n  {}\n\nThis requires confirmation before execution.",
            package, cmd_str
        ))
        .with_commands(vec![cmd_str])
    }

    /// List installed packages
    fn list_installed(&self, filter: Option<&str>) -> AgentResponse {
        let (cmd, args): (&str, Vec<&str>) = match self.package_manager {
            PackageManager::Apt => ("dpkg", vec!["-l"]),
            PackageManager::Pacman => ("pacman", vec!["-Q"]),
            PackageManager::Dnf => ("dnf", vec!["list", "installed"]),
            PackageManager::Yum => ("yum", vec!["list", "installed"]),
            PackageManager::Zypper => ("zypper", vec!["packages", "--installed-only"]),
            PackageManager::Brew => ("brew", vec!["list"]),
            PackageManager::Nix => ("nix-env", vec!["-q"]),
            PackageManager::Unknown => {
                return AgentResponse::error("No package manager detected".to_string());
            }
        };

        match self.execute_command(cmd, &args) {
            Ok(output) => {
                let filtered_output = if let Some(f) = filter {
                    output
                        .lines()
                        .filter(|line| line.to_lowercase().contains(&f.to_lowercase()))
                        .collect::<Vec<_>>()
                        .join("\n")
                } else {
                    output
                };

                let cmd_str = format!("{} {}", cmd, args.join(" "));
                AgentResponse::success(filtered_output)
                    .with_commands(vec![cmd_str])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Check for updates
    fn check_updates(&self) -> AgentResponse {
        let (cmd, args): (&str, Vec<&str>) = match self.package_manager {
            PackageManager::Apt => ("apt", vec!["list", "--upgradable"]),
            PackageManager::Pacman => ("pacman", vec!["-Qu"]),
            PackageManager::Dnf => ("dnf", vec!["check-update"]),
            PackageManager::Yum => ("yum", vec!["check-update"]),
            PackageManager::Zypper => ("zypper", vec!["list-updates"]),
            PackageManager::Brew => ("brew", vec!["outdated"]),
            PackageManager::Nix => ("nix-channel", vec!["--update"]),
            PackageManager::Unknown => {
                return AgentResponse::error("No package manager detected".to_string());
            }
        };

        // Note: apt requires update first
        if self.package_manager == PackageManager::Apt {
            let _ = self.execute_command("sudo", &["apt", "update"]);
        }

        match self.execute_command(cmd, &args) {
            Ok(output) => {
                let cmd_str = format!("{} {}", cmd, args.join(" "));
                AgentResponse::success(if output.trim().is_empty() {
                    "All packages are up to date!".to_string()
                } else {
                    output
                })
                .with_commands(vec![cmd_str])
                .with_suggestions(vec!["upgrade all packages".to_string()])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Upgrade all packages (returns command to run)
    fn upgrade_packages(&self) -> AgentResponse {
        let cmd_str = match self.package_manager {
            PackageManager::Apt => "sudo apt upgrade -y".to_string(),
            PackageManager::Pacman => "sudo pacman -Syu".to_string(),
            PackageManager::Dnf => "sudo dnf upgrade -y".to_string(),
            PackageManager::Yum => "sudo yum update -y".to_string(),
            PackageManager::Zypper => "sudo zypper update -y".to_string(),
            PackageManager::Brew => "brew upgrade".to_string(),
            PackageManager::Nix => "nix-env -u".to_string(),
            PackageManager::Unknown => {
                return AgentResponse::error("No package manager detected".to_string());
            }
        };

        AgentResponse::success(format!(
            "To upgrade all packages, run:\n\n  {}\n\nThis requires confirmation before execution.",
            cmd_str
        ))
        .with_commands(vec![cmd_str])
    }

    /// Get package info
    fn package_info(&self, package: &str) -> AgentResponse {
        let (cmd, args): (&str, Vec<&str>) = match self.package_manager {
            PackageManager::Apt => ("apt", vec!["show", package]),
            PackageManager::Pacman => ("pacman", vec!["-Si", package]),
            PackageManager::Dnf => ("dnf", vec!["info", package]),
            PackageManager::Yum => ("yum", vec!["info", package]),
            PackageManager::Zypper => ("zypper", vec!["info", package]),
            PackageManager::Brew => ("brew", vec!["info", package]),
            PackageManager::Nix => ("nix-env", vec!["-qaP", "--description", package]),
            PackageManager::Unknown => {
                return AgentResponse::error("No package manager detected".to_string());
            }
        };

        match self.execute_command(cmd, &args) {
            Ok(output) => {
                let cmd_str = format!("{} {}", cmd, args.join(" "));
                AgentResponse::success(output)
                    .with_commands(vec![cmd_str])
                    .with_suggestions(vec![
                        format!("install {}", package),
                    ])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// List package files
    fn list_package_files(&self, package: &str) -> AgentResponse {
        let (cmd, args): (&str, Vec<&str>) = match self.package_manager {
            PackageManager::Apt => ("dpkg", vec!["-L", package]),
            PackageManager::Pacman => ("pacman", vec!["-Ql", package]),
            PackageManager::Dnf => ("rpm", vec!["-ql", package]),
            PackageManager::Yum => ("rpm", vec!["-ql", package]),
            PackageManager::Zypper => ("rpm", vec!["-ql", package]),
            PackageManager::Brew => ("brew", vec!["list", "--verbose", package]),
            PackageManager::Nix => {
                return AgentResponse::error("Nix doesn't support listing package files directly".to_string());
            }
            PackageManager::Unknown => {
                return AgentResponse::error("No package manager detected".to_string());
            }
        };

        match self.execute_command(cmd, &args) {
            Ok(output) => {
                let cmd_str = format!("{} {}", cmd, args.join(" "));
                AgentResponse::success(output).with_commands(vec![cmd_str])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Find which package owns a file
    fn who_owns(&self, file: &str) -> AgentResponse {
        let (cmd, args): (&str, Vec<&str>) = match self.package_manager {
            PackageManager::Apt => ("dpkg", vec!["-S", file]),
            PackageManager::Pacman => ("pacman", vec!["-Qo", file]),
            PackageManager::Dnf => ("rpm", vec!["-qf", file]),
            PackageManager::Yum => ("rpm", vec!["-qf", file]),
            PackageManager::Zypper => ("rpm", vec!["-qf", file]),
            PackageManager::Brew => {
                return AgentResponse::error("Homebrew doesn't support 'which package owns' directly".to_string());
            }
            PackageManager::Nix => {
                return AgentResponse::error("Use 'nix-locate' for this functionality".to_string());
            }
            PackageManager::Unknown => {
                return AgentResponse::error("No package manager detected".to_string());
            }
        };

        match self.execute_command(cmd, &args) {
            Ok(output) => {
                let cmd_str = format!("{} {}", cmd, args.join(" "));
                AgentResponse::success(output).with_commands(vec![cmd_str])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Clean package cache
    fn clean_cache(&self) -> AgentResponse {
        let cmd_str = match self.package_manager {
            PackageManager::Apt => "sudo apt clean && sudo apt autoremove -y".to_string(),
            PackageManager::Pacman => "sudo pacman -Sc".to_string(),
            PackageManager::Dnf => "sudo dnf clean all".to_string(),
            PackageManager::Yum => "sudo yum clean all".to_string(),
            PackageManager::Zypper => "sudo zypper clean".to_string(),
            PackageManager::Brew => "brew cleanup".to_string(),
            PackageManager::Nix => "nix-collect-garbage -d".to_string(),
            PackageManager::Unknown => {
                return AgentResponse::error("No package manager detected".to_string());
            }
        };

        AgentResponse::success(format!(
            "To clean package cache, run:\n\n  {}\n\nThis requires confirmation before execution.",
            cmd_str
        ))
        .with_commands(vec![cmd_str])
    }

    /// Handle unknown command
    fn handle_unknown(&self, command: &str) -> AgentResponse {
        AgentResponse::error(format!(
            "Unknown package command: {}. Detected package manager: {}",
            command,
            self.package_manager.name()
        ))
        .with_suggestions(vec![
            "search nodejs".to_string(),
            "install vim".to_string(),
            "list installed".to_string(),
            "check updates".to_string(),
        ])
    }
}

impl Default for PackageAgent {
    fn default() -> Self {
        Self::new()
    }
}

impl Agent for PackageAgent {
    fn name(&self) -> &str {
        "package"
    }

    fn description(&self) -> &str {
        "Package installation and management"
    }

    fn capabilities(&self) -> &[AgentCapability] {
        &self.capabilities
    }

    fn can_handle(&self, request: &AgentRequest) -> bool {
        // Handle if explicitly targeted at package agent
        if request.agent == "package" || request.agent == "pkg"
            || request.agent == "apt" || request.agent == "dnf"
            || request.agent == "pacman" || request.agent == "brew"
        {
            return true;
        }

        // Check if the command matches package-related keywords
        let cmd_lower = request.command.to_lowercase();
        cmd_lower.contains("package")
            || cmd_lower.contains("install")
            || cmd_lower.contains("uninstall")
            || cmd_lower.contains("upgrade")
            || cmd_lower.contains("apt ")
            || cmd_lower.contains("pacman")
            || cmd_lower.contains("brew ")
    }

    fn handle(&self, request: AgentRequest) -> AgentResponse {
        let command = PackageCommand::parse(&request.command);

        match command {
            PackageCommand::Search { query } => self.search_packages(&query),
            PackageCommand::Install { package } => self.install_package(&package),
            PackageCommand::Remove { package } => self.remove_package(&package),
            PackageCommand::ListInstalled { filter } => self.list_installed(filter.as_deref()),
            PackageCommand::CheckUpdates => self.check_updates(),
            PackageCommand::Upgrade => self.upgrade_packages(),
            PackageCommand::Info { package } => self.package_info(&package),
            PackageCommand::ListFiles { package } => self.list_package_files(&package),
            PackageCommand::WhoOwns { file } => self.who_owns(&file),
            PackageCommand::Clean => self.clean_cache(),
            PackageCommand::Unknown(cmd) => self.handle_unknown(&cmd),
        }
    }

    fn examples(&self) -> &[&str] {
        &[
            "search nodejs",
            "install vim",
            "remove unused-package",
            "list installed",
            "check updates",
            "upgrade all packages",
            "info nginx",
            "which package owns /usr/bin/vim",
        ]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_search() {
        assert!(matches!(
            PackageCommand::parse("search nodejs"),
            PackageCommand::Search { query } if query == "nodejs"
        ));
    }

    #[test]
    fn test_parse_install() {
        assert!(matches!(
            PackageCommand::parse("install vim"),
            PackageCommand::Install { package } if package == "vim"
        ));
    }

    #[test]
    fn test_parse_check_updates() {
        assert!(matches!(
            PackageCommand::parse("check for updates"),
            PackageCommand::CheckUpdates
        ));
    }

    #[test]
    fn test_agent_can_handle() {
        let agent = PackageAgent::new();

        let req = AgentRequest::new("package", "search vim");
        assert!(agent.can_handle(&req));

        let req = AgentRequest::new("other", "install nodejs");
        assert!(agent.can_handle(&req));
    }
}
