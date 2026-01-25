//! CX Linux Agent System
//!
//! Provides integration with CX Linux system agents for
//! intelligent system management.

#![allow(dead_code)]

mod docker;
mod file;
mod git;
mod package;
mod runtime;
mod system;
mod traits;

// Re-export agents
pub use docker::DockerAgent;
pub use file::FileAgent;
pub use git::GitAgent;
pub use package::PackageAgent;
pub use runtime::AgentRuntime;
pub use system::SystemAgent;
pub use traits::{Agent, AgentCapability, AgentRequest, AgentResponse};

/// Available built-in agents
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum BuiltinAgent {
    /// System information and management
    System,
    /// File system operations
    File,
    /// Package management
    Package,
    /// Network configuration and monitoring
    Network,
    /// Process management
    Process,
    /// Git operations
    Git,
    /// Docker/container management
    Docker,
}

impl BuiltinAgent {
    pub fn name(&self) -> &'static str {
        match self {
            Self::System => "system",
            Self::File => "file",
            Self::Package => "package",
            Self::Network => "network",
            Self::Process => "process",
            Self::Git => "git",
            Self::Docker => "docker",
        }
    }

    pub fn description(&self) -> &'static str {
        match self {
            Self::System => "System information, services, and configuration",
            Self::File => "File and directory operations",
            Self::Package => "Package installation and management",
            Self::Network => "Network configuration and monitoring",
            Self::Process => "Process management and monitoring",
            Self::Git => "Git repository operations",
            Self::Docker => "Container and image management",
        }
    }

    pub fn icon(&self) -> &'static str {
        match self {
            Self::System => "󰒋",   // nf-md-cog
            Self::File => "󰉋",    // nf-md-folder
            Self::Package => "󰏗", // nf-md-package
            Self::Network => "󰖩", // nf-md-network
            Self::Process => "󰓛", // nf-md-chart_bar
            Self::Git => "",      // nf-dev-git
            Self::Docker => "󰡨",  // nf-md-docker
        }
    }

    pub fn from_name(name: &str) -> Option<Self> {
        match name.to_lowercase().as_str() {
            "system" | "sys" => Some(Self::System),
            "file" | "files" | "fs" => Some(Self::File),
            "package" | "pkg" | "apt" | "dnf" | "pacman" => Some(Self::Package),
            "network" | "net" => Some(Self::Network),
            "process" | "proc" | "ps" => Some(Self::Process),
            "git" => Some(Self::Git),
            "docker" | "container" | "podman" => Some(Self::Docker),
            _ => None,
        }
    }

    pub fn all() -> &'static [Self] {
        &[
            Self::System,
            Self::File,
            Self::Package,
            Self::Network,
            Self::Process,
            Self::Git,
            Self::Docker,
        ]
    }
}

/// Example agent commands
pub mod examples {
    use super::BuiltinAgent;

    pub fn for_agent(agent: BuiltinAgent) -> &'static [&'static str] {
        match agent {
            BuiltinAgent::System => &[
                "show system info",
                "list running services",
                "check disk usage",
                "show memory usage",
                "restart service nginx",
            ],
            BuiltinAgent::File => &[
                "find large files",
                "search for *.log files",
                "show recent files",
                "calculate directory size",
            ],
            BuiltinAgent::Package => &[
                "install nodejs",
                "update all packages",
                "search for python packages",
                "remove unused packages",
            ],
            BuiltinAgent::Network => &[
                "show network interfaces",
                "check port 8080",
                "list open connections",
                "test connectivity to google.com",
            ],
            BuiltinAgent::Process => &[
                "show top processes",
                "find processes using port 3000",
                "kill process 1234",
                "show process tree",
            ],
            BuiltinAgent::Git => &[
                "show status",
                "list branches",
                "show recent commits",
                "create branch feature/new",
            ],
            BuiltinAgent::Docker => &[
                "list containers",
                "show running containers",
                "pull image nginx:latest",
                "stop container web",
            ],
        }
    }
}

/// Create a runtime with all built-in agents registered
pub fn create_runtime() -> AgentRuntime {
    let mut runtime = AgentRuntime::new();
    runtime.register_builtin_agents();
    runtime.enable();
    runtime
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_create_runtime() {
        let runtime = create_runtime();
        assert!(runtime.is_enabled());
        assert!(runtime.get("system").is_some());
        assert!(runtime.get("file").is_some());
        assert!(runtime.get("package").is_some());
        assert!(runtime.get("git").is_some());
        assert!(runtime.get("docker").is_some());
    }

    #[test]
    fn test_builtin_agent_from_name() {
        assert_eq!(BuiltinAgent::from_name("system"), Some(BuiltinAgent::System));
        assert_eq!(BuiltinAgent::from_name("git"), Some(BuiltinAgent::Git));
        assert_eq!(BuiltinAgent::from_name("docker"), Some(BuiltinAgent::Docker));
        assert_eq!(BuiltinAgent::from_name("unknown"), None);
    }
}
