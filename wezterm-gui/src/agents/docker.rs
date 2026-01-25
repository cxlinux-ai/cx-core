//! Docker Agent - Container and image management
//!
//! Provides capabilities for:
//! - Listing containers
//! - Starting/stopping containers
//! - Viewing logs
//! - Listing images
//! - Running containers

use super::traits::{Agent, AgentCapability, AgentRequest, AgentResponse};
use std::process::Command;

/// Container runtime type
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ContainerRuntime {
    Docker,
    Podman,
    Nerdctl,
    Unknown,
}

impl ContainerRuntime {
    /// Detect the available container runtime
    pub fn detect() -> Self {
        if Self::command_exists("docker") {
            Self::Docker
        } else if Self::command_exists("podman") {
            Self::Podman
        } else if Self::command_exists("nerdctl") {
            Self::Nerdctl
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

    /// Get the command name
    pub fn command(&self) -> &'static str {
        match self {
            Self::Docker => "docker",
            Self::Podman => "podman",
            Self::Nerdctl => "nerdctl",
            Self::Unknown => "docker",
        }
    }
}

/// Commands that the docker agent can handle
#[derive(Debug, Clone, PartialEq)]
pub enum DockerCommand {
    /// List containers
    ListContainers { all: bool },
    /// Start a container
    Start { container: String },
    /// Stop a container
    Stop { container: String },
    /// Restart a container
    Restart { container: String },
    /// Remove a container
    Remove { container: String, force: bool },
    /// View container logs
    Logs { container: String, tail: Option<usize>, follow: bool },
    /// Execute command in container
    Exec { container: String, command: String },
    /// Inspect container
    Inspect { container: String },
    /// List images
    ListImages,
    /// Pull an image
    Pull { image: String },
    /// Remove an image
    RemoveImage { image: String, force: bool },
    /// Build image
    Build { tag: Option<String>, path: String },
    /// Run a new container
    Run { image: String, name: Option<String>, ports: Vec<String>, detach: bool },
    /// Show container stats
    Stats,
    /// Prune unused resources
    Prune { what: String },
    /// List networks
    ListNetworks,
    /// List volumes
    ListVolumes,
    /// Docker compose up
    ComposeUp { detach: bool },
    /// Docker compose down
    ComposeDown,
    /// Unknown command
    Unknown(String),
}

impl DockerCommand {
    /// Parse a command string into a DockerCommand
    pub fn parse(input: &str) -> Self {
        let input_lower = input.to_lowercase();
        let words: Vec<&str> = input.split_whitespace().collect();

        // List containers
        if input_lower.contains("container") && input_lower.contains("list")
            || input_lower == "ps" || input_lower.contains("docker ps")
        {
            let all = input_lower.contains("all") || input_lower.contains("-a");
            return Self::ListContainers { all };
        }

        // Compose
        if input_lower.contains("compose") {
            if input_lower.contains("down") {
                return Self::ComposeDown;
            }
            let detach = input_lower.contains("-d") || input_lower.contains("detach")
                || input_lower.contains("background");
            return Self::ComposeUp { detach };
        }

        // Start container
        if input_lower.contains("start") && !input_lower.contains("restart") {
            if let Some(container) = Self::extract_container_name(&words, "start") {
                return Self::Start { container };
            }
        }

        // Stop container
        if input_lower.contains("stop") {
            if let Some(container) = Self::extract_container_name(&words, "stop") {
                return Self::Stop { container };
            }
        }

        // Restart container
        if input_lower.contains("restart") {
            if let Some(container) = Self::extract_container_name(&words, "restart") {
                return Self::Restart { container };
            }
        }

        // Remove container
        if (input_lower.contains("remove") || input_lower.contains("rm"))
            && input_lower.contains("container")
        {
            let force = input_lower.contains("force") || input_lower.contains("-f");
            if let Some(container) = Self::extract_container_name(&words, "container") {
                return Self::Remove { container, force };
            }
        }

        // Logs
        if input_lower.contains("log") {
            let follow = input_lower.contains("follow") || input_lower.contains("-f");
            let tail = words.iter()
                .filter_map(|w| w.parse::<usize>().ok())
                .next();
            if let Some(container) = Self::extract_container_name(&words, "logs") {
                return Self::Logs { container, tail, follow };
            }
        }

        // Exec
        if input_lower.contains("exec") || input_lower.contains("shell") {
            if let Some(container) = Self::extract_container_name(&words, "exec") {
                let command = if input_lower.contains("shell") {
                    "/bin/sh".to_string()
                } else {
                    // Try to extract command after container name
                    words.iter()
                        .skip_while(|&w| w.to_lowercase() != "exec" && w.to_lowercase() != container.to_lowercase())
                        .skip(2)
                        .map(|s| *s)
                        .collect::<Vec<_>>()
                        .join(" ")
                };
                let command = if command.is_empty() { "/bin/sh".to_string() } else { command };
                return Self::Exec { container, command };
            }
        }

        // Inspect
        if input_lower.contains("inspect") || input_lower.contains("details") {
            if let Some(container) = Self::extract_container_name(&words, "inspect") {
                return Self::Inspect { container };
            }
        }

        // List images
        if input_lower.contains("image") && input_lower.contains("list")
            || input_lower == "images"
        {
            return Self::ListImages;
        }

        // Pull image
        if input_lower.contains("pull") {
            if let Some(image) = Self::extract_image_name(&words, "pull") {
                return Self::Pull { image };
            }
        }

        // Remove image
        if (input_lower.contains("remove") || input_lower.contains("rmi"))
            && input_lower.contains("image")
        {
            let force = input_lower.contains("force") || input_lower.contains("-f");
            if let Some(image) = Self::extract_image_name(&words, "image") {
                return Self::RemoveImage { image, force };
            }
        }

        // Build
        if input_lower.contains("build") {
            let tag = words.iter()
                .position(|&w| w == "-t" || w == "--tag")
                .and_then(|i| words.get(i + 1))
                .map(|s| s.to_string());
            let path = words.last()
                .filter(|w| w.starts_with('.') || w.starts_with('/'))
                .map(|s| s.to_string())
                .unwrap_or(".".to_string());
            return Self::Build { tag, path };
        }

        // Run
        if input_lower.contains("run") {
            let detach = input_lower.contains("-d") || input_lower.contains("detach")
                || input_lower.contains("background");
            let name = words.iter()
                .position(|&w| w == "--name")
                .and_then(|i| words.get(i + 1))
                .map(|s| s.to_string());

            // Extract ports
            let mut ports = Vec::new();
            let mut i = 0;
            while i < words.len() {
                if words[i] == "-p" || words[i] == "--publish" {
                    if let Some(port) = words.get(i + 1) {
                        ports.push(port.to_string());
                    }
                    i += 2;
                } else {
                    i += 1;
                }
            }

            if let Some(image) = Self::extract_image_name(&words, "run") {
                return Self::Run { image, name, ports, detach };
            }
        }

        // Stats
        if input_lower.contains("stats") || input_lower.contains("resource") {
            return Self::Stats;
        }

        // Prune
        if input_lower.contains("prune") || input_lower.contains("clean") {
            let what = if input_lower.contains("container") {
                "containers"
            } else if input_lower.contains("image") {
                "images"
            } else if input_lower.contains("volume") {
                "volumes"
            } else if input_lower.contains("network") {
                "networks"
            } else {
                "system"
            };
            return Self::Prune { what: what.to_string() };
        }

        // Networks
        if input_lower.contains("network") && input_lower.contains("list") {
            return Self::ListNetworks;
        }

        // Volumes
        if input_lower.contains("volume") && input_lower.contains("list") {
            return Self::ListVolumes;
        }

        // Simple container listing
        if input_lower.contains("container") || input_lower.contains("running") {
            return Self::ListContainers { all: false };
        }

        Self::Unknown(input.to_string())
    }

    /// Extract container name from words
    fn extract_container_name(words: &[&str], after_keyword: &str) -> Option<String> {
        words.iter()
            .skip_while(|&w| w.to_lowercase() != after_keyword)
            .nth(1)
            .or_else(|| words.last())
            .map(|s| s.to_string())
    }

    /// Extract image name from words
    fn extract_image_name(words: &[&str], after_keyword: &str) -> Option<String> {
        words.iter()
            .skip_while(|&w| w.to_lowercase() != after_keyword)
            .nth(1)
            .filter(|w| !w.starts_with('-'))
            .or_else(|| words.iter().find(|w| w.contains(':') || w.contains('/')))
            .map(|s| s.to_string())
    }
}

/// Docker agent for container management
pub struct DockerAgent {
    capabilities: Vec<AgentCapability>,
    runtime: ContainerRuntime,
}

impl DockerAgent {
    /// Create a new docker agent
    pub fn new() -> Self {
        Self {
            capabilities: vec![
                AgentCapability::Execute,
                AgentCapability::Custom("docker".to_string()),
            ],
            runtime: ContainerRuntime::detect(),
        }
    }

    /// Execute a docker command and return output
    fn execute_docker(&self, args: &[&str]) -> Result<String, String> {
        let cmd = self.runtime.command();
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

    /// Check if docker/podman is available
    fn is_available(&self) -> bool {
        self.runtime != ContainerRuntime::Unknown
    }

    /// List containers
    fn list_containers(&self, all: bool) -> AgentResponse {
        if !self.is_available() {
            return AgentResponse::error("No container runtime found (docker/podman)".to_string());
        }

        let mut args = vec!["ps", "--format", "table {{.ID}}\t{{.Image}}\t{{.Status}}\t{{.Names}}"];
        if all {
            args.insert(1, "-a");
        }

        match self.execute_docker(&args) {
            Ok(output) => {
                let cmd = format!("{} ps{}", self.runtime.command(), if all { " -a" } else { "" });
                let result = if output.trim().is_empty() || output.lines().count() <= 1 {
                    "No containers found".to_string()
                } else {
                    output
                };
                AgentResponse::success(result)
                    .with_commands(vec![cmd])
                    .with_suggestions(vec![
                        "list images".to_string(),
                        "show container logs".to_string(),
                    ])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Start a container
    fn start_container(&self, container: &str) -> AgentResponse {
        if !self.is_available() {
            return AgentResponse::error("No container runtime found".to_string());
        }

        match self.execute_docker(&["start", container]) {
            Ok(_) => {
                AgentResponse::success(format!("Started container: {}", container))
                    .with_commands(vec![format!("{} start {}", self.runtime.command(), container)])
                    .with_suggestions(vec![
                        format!("logs {}", container),
                        "list containers".to_string(),
                    ])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Stop a container
    fn stop_container(&self, container: &str) -> AgentResponse {
        if !self.is_available() {
            return AgentResponse::error("No container runtime found".to_string());
        }

        match self.execute_docker(&["stop", container]) {
            Ok(_) => {
                AgentResponse::success(format!("Stopped container: {}", container))
                    .with_commands(vec![format!("{} stop {}", self.runtime.command(), container)])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Restart a container
    fn restart_container(&self, container: &str) -> AgentResponse {
        if !self.is_available() {
            return AgentResponse::error("No container runtime found".to_string());
        }

        match self.execute_docker(&["restart", container]) {
            Ok(_) => {
                AgentResponse::success(format!("Restarted container: {}", container))
                    .with_commands(vec![format!("{} restart {}", self.runtime.command(), container)])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Remove a container
    fn remove_container(&self, container: &str, force: bool) -> AgentResponse {
        if !self.is_available() {
            return AgentResponse::error("No container runtime found".to_string());
        }

        let cmd = if force {
            format!("{} rm -f {}", self.runtime.command(), container)
        } else {
            format!("{} rm {}", self.runtime.command(), container)
        };

        AgentResponse::success(format!(
            "To remove container '{}', run:\n\n  {}\n\nThis requires confirmation before execution.",
            container, cmd
        ))
        .with_commands(vec![cmd])
    }

    /// View container logs
    fn container_logs(&self, container: &str, tail: Option<usize>, follow: bool) -> AgentResponse {
        if !self.is_available() {
            return AgentResponse::error("No container runtime found".to_string());
        }

        let mut args = vec!["logs"];
        let tail_str;
        if let Some(n) = tail {
            args.push("--tail");
            tail_str = n.to_string();
            args.push(&tail_str);
        }
        if follow {
            // Don't actually follow in non-interactive mode
            args.push("--tail");
            args.push("50");
        }
        args.push(container);

        match self.execute_docker(&args) {
            Ok(output) => {
                let cmd = format!("{} {}", self.runtime.command(), args.join(" "));
                AgentResponse::success(output)
                    .with_commands(vec![cmd])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Execute command in container
    fn exec_in_container(&self, container: &str, command: &str) -> AgentResponse {
        if !self.is_available() {
            return AgentResponse::error("No container runtime found".to_string());
        }

        let cmd = format!("{} exec -it {} {}", self.runtime.command(), container, command);

        AgentResponse::success(format!(
            "To execute in container '{}', run:\n\n  {}\n\nThis opens an interactive session.",
            container, cmd
        ))
        .with_commands(vec![cmd])
    }

    /// Inspect container
    fn inspect_container(&self, container: &str) -> AgentResponse {
        if !self.is_available() {
            return AgentResponse::error("No container runtime found".to_string());
        }

        match self.execute_docker(&["inspect", container]) {
            Ok(output) => {
                let cmd = format!("{} inspect {}", self.runtime.command(), container);
                AgentResponse::success(output)
                    .with_commands(vec![cmd])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// List images
    fn list_images(&self) -> AgentResponse {
        if !self.is_available() {
            return AgentResponse::error("No container runtime found".to_string());
        }

        match self.execute_docker(&["images", "--format", "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.ID}}"]) {
            Ok(output) => {
                let cmd = format!("{} images", self.runtime.command());
                AgentResponse::success(output)
                    .with_commands(vec![cmd])
                    .with_suggestions(vec![
                        "pull nginx:latest".to_string(),
                        "list containers".to_string(),
                    ])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Pull an image
    fn pull_image(&self, image: &str) -> AgentResponse {
        if !self.is_available() {
            return AgentResponse::error("No container runtime found".to_string());
        }

        let cmd = format!("{} pull {}", self.runtime.command(), image);

        AgentResponse::success(format!(
            "To pull image '{}', run:\n\n  {}\n\nThis may take a while depending on image size.",
            image, cmd
        ))
        .with_commands(vec![cmd])
    }

    /// Remove an image
    fn remove_image(&self, image: &str, force: bool) -> AgentResponse {
        if !self.is_available() {
            return AgentResponse::error("No container runtime found".to_string());
        }

        let cmd = if force {
            format!("{} rmi -f {}", self.runtime.command(), image)
        } else {
            format!("{} rmi {}", self.runtime.command(), image)
        };

        AgentResponse::success(format!(
            "To remove image '{}', run:\n\n  {}\n\nThis requires confirmation before execution.",
            image, cmd
        ))
        .with_commands(vec![cmd])
    }

    /// Build image
    fn build_image(&self, tag: Option<&str>, path: &str) -> AgentResponse {
        if !self.is_available() {
            return AgentResponse::error("No container runtime found".to_string());
        }

        let cmd = if let Some(t) = tag {
            format!("{} build -t {} {}", self.runtime.command(), t, path)
        } else {
            format!("{} build {}", self.runtime.command(), path)
        };

        AgentResponse::success(format!(
            "To build image, run:\n\n  {}\n\nThis may take a while.",
            cmd
        ))
        .with_commands(vec![cmd])
    }

    /// Run a container
    fn run_container(&self, image: &str, name: Option<&str>, ports: &[String], detach: bool) -> AgentResponse {
        if !self.is_available() {
            return AgentResponse::error("No container runtime found".to_string());
        }

        let mut cmd = format!("{} run", self.runtime.command());
        if detach {
            cmd.push_str(" -d");
        }
        if let Some(n) = name {
            cmd.push_str(&format!(" --name {}", n));
        }
        for port in ports {
            cmd.push_str(&format!(" -p {}", port));
        }
        cmd.push_str(&format!(" {}", image));

        AgentResponse::success(format!(
            "To run container, execute:\n\n  {}\n\nThis requires confirmation.",
            cmd
        ))
        .with_commands(vec![cmd])
    }

    /// Show container stats
    fn container_stats(&self) -> AgentResponse {
        if !self.is_available() {
            return AgentResponse::error("No container runtime found".to_string());
        }

        // Use --no-stream to get a single snapshot
        match self.execute_docker(&["stats", "--no-stream", "--format", "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"]) {
            Ok(output) => {
                let cmd = format!("{} stats --no-stream", self.runtime.command());
                AgentResponse::success(output)
                    .with_commands(vec![cmd])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Prune unused resources
    fn prune(&self, what: &str) -> AgentResponse {
        if !self.is_available() {
            return AgentResponse::error("No container runtime found".to_string());
        }

        let cmd = match what {
            "containers" => format!("{} container prune -f", self.runtime.command()),
            "images" => format!("{} image prune -f", self.runtime.command()),
            "volumes" => format!("{} volume prune -f", self.runtime.command()),
            "networks" => format!("{} network prune -f", self.runtime.command()),
            _ => format!("{} system prune -f", self.runtime.command()),
        };

        AgentResponse::success(format!(
            "To prune {}, run:\n\n  {}\n\nThis will remove unused resources.",
            what, cmd
        ))
        .with_commands(vec![cmd])
    }

    /// List networks
    fn list_networks(&self) -> AgentResponse {
        if !self.is_available() {
            return AgentResponse::error("No container runtime found".to_string());
        }

        match self.execute_docker(&["network", "ls"]) {
            Ok(output) => {
                let cmd = format!("{} network ls", self.runtime.command());
                AgentResponse::success(output)
                    .with_commands(vec![cmd])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// List volumes
    fn list_volumes(&self) -> AgentResponse {
        if !self.is_available() {
            return AgentResponse::error("No container runtime found".to_string());
        }

        match self.execute_docker(&["volume", "ls"]) {
            Ok(output) => {
                let cmd = format!("{} volume ls", self.runtime.command());
                AgentResponse::success(output)
                    .with_commands(vec![cmd])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Docker compose up
    fn compose_up(&self, detach: bool) -> AgentResponse {
        let cmd = if detach {
            "docker compose up -d"
        } else {
            "docker compose up"
        };

        AgentResponse::success(format!(
            "To start services with compose, run:\n\n  {}\n\nThis requires a docker-compose.yml file.",
            cmd
        ))
        .with_commands(vec![cmd.to_string()])
    }

    /// Docker compose down
    fn compose_down(&self) -> AgentResponse {
        let cmd = "docker compose down";

        AgentResponse::success(format!(
            "To stop compose services, run:\n\n  {}\n\nThis will stop and remove containers.",
            cmd
        ))
        .with_commands(vec![cmd.to_string()])
    }

    /// Handle unknown command
    fn handle_unknown(&self, command: &str) -> AgentResponse {
        AgentResponse::error(format!(
            "Unknown docker command: {}. Runtime: {}",
            command,
            self.runtime.command()
        ))
        .with_suggestions(vec![
            "list containers".to_string(),
            "list images".to_string(),
            "show stats".to_string(),
            "pull nginx:latest".to_string(),
        ])
    }
}

impl Default for DockerAgent {
    fn default() -> Self {
        Self::new()
    }
}

impl Agent for DockerAgent {
    fn name(&self) -> &str {
        "docker"
    }

    fn description(&self) -> &str {
        "Container and image management"
    }

    fn capabilities(&self) -> &[AgentCapability] {
        &self.capabilities
    }

    fn can_handle(&self, request: &AgentRequest) -> bool {
        // Handle if explicitly targeted at docker agent
        if request.agent == "docker" || request.agent == "container"
            || request.agent == "podman"
        {
            return true;
        }

        // Check if the command matches docker-related keywords
        let cmd_lower = request.command.to_lowercase();
        cmd_lower.contains("docker")
            || cmd_lower.contains("container")
            || cmd_lower.contains("image")
            || cmd_lower.contains("podman")
            || cmd_lower.contains("compose")
    }

    fn handle(&self, request: AgentRequest) -> AgentResponse {
        let command = DockerCommand::parse(&request.command);

        match command {
            DockerCommand::ListContainers { all } => self.list_containers(all),
            DockerCommand::Start { container } => self.start_container(&container),
            DockerCommand::Stop { container } => self.stop_container(&container),
            DockerCommand::Restart { container } => self.restart_container(&container),
            DockerCommand::Remove { container, force } => self.remove_container(&container, force),
            DockerCommand::Logs { container, tail, follow } => {
                self.container_logs(&container, tail, follow)
            }
            DockerCommand::Exec { container, command } => self.exec_in_container(&container, &command),
            DockerCommand::Inspect { container } => self.inspect_container(&container),
            DockerCommand::ListImages => self.list_images(),
            DockerCommand::Pull { image } => self.pull_image(&image),
            DockerCommand::RemoveImage { image, force } => self.remove_image(&image, force),
            DockerCommand::Build { tag, path } => self.build_image(tag.as_deref(), &path),
            DockerCommand::Run { image, name, ports, detach } => {
                self.run_container(&image, name.as_deref(), &ports, detach)
            }
            DockerCommand::Stats => self.container_stats(),
            DockerCommand::Prune { what } => self.prune(&what),
            DockerCommand::ListNetworks => self.list_networks(),
            DockerCommand::ListVolumes => self.list_volumes(),
            DockerCommand::ComposeUp { detach } => self.compose_up(detach),
            DockerCommand::ComposeDown => self.compose_down(),
            DockerCommand::Unknown(cmd) => self.handle_unknown(&cmd),
        }
    }

    fn examples(&self) -> &[&str] {
        &[
            "list containers",
            "list all containers",
            "list images",
            "start container myapp",
            "stop container myapp",
            "logs myapp",
            "pull nginx:latest",
            "run nginx:latest -p 8080:80 -d",
            "show stats",
            "compose up -d",
            "compose down",
        ]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_list_containers() {
        assert!(matches!(
            DockerCommand::parse("list containers"),
            DockerCommand::ListContainers { all: false }
        ));
        assert!(matches!(
            DockerCommand::parse("list all containers"),
            DockerCommand::ListContainers { all: true }
        ));
    }

    #[test]
    fn test_parse_stop() {
        assert!(matches!(
            DockerCommand::parse("stop myapp"),
            DockerCommand::Stop { container } if container == "myapp"
        ));
    }

    #[test]
    fn test_parse_logs() {
        assert!(matches!(
            DockerCommand::parse("logs myapp"),
            DockerCommand::Logs { container, tail: None, follow: false } if container == "myapp"
        ));
    }

    #[test]
    fn test_parse_pull() {
        assert!(matches!(
            DockerCommand::parse("pull nginx:latest"),
            DockerCommand::Pull { image } if image == "nginx:latest"
        ));
    }

    #[test]
    fn test_agent_can_handle() {
        let agent = DockerAgent::new();

        let req = AgentRequest::new("docker", "list containers");
        assert!(agent.can_handle(&req));

        let req = AgentRequest::new("other", "list docker containers");
        assert!(agent.can_handle(&req));
    }
}
