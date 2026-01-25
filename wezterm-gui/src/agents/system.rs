//! System Agent - System information and management
//!
//! Provides capabilities for:
//! - Getting system info (uname, hostname, uptime)
//! - Listing processes (ps aux)
//! - Checking services (systemctl status)
//! - Getting disk usage (df -h)
//! - Getting memory usage (free -h)

use super::traits::{Agent, AgentCapability, AgentRequest, AgentResponse};
use std::process::Command;

/// Commands that the system agent can handle
#[derive(Debug, Clone, PartialEq)]
pub enum SystemCommand {
    /// Get system information (uname -a)
    SystemInfo,
    /// Get hostname
    Hostname,
    /// Get system uptime
    Uptime,
    /// List processes
    ListProcesses,
    /// List top processes by CPU/memory
    TopProcesses { count: usize },
    /// Check service status
    ServiceStatus { service: String },
    /// List services
    ListServices,
    /// Get disk usage
    DiskUsage,
    /// Get memory usage
    MemoryUsage,
    /// Get CPU info
    CpuInfo,
    /// Get load average
    LoadAverage,
    /// Unknown command - try to execute as-is
    Unknown(String),
}

impl SystemCommand {
    /// Parse a command string into a SystemCommand
    pub fn parse(input: &str) -> Self {
        let input_lower = input.to_lowercase();
        let words: Vec<&str> = input_lower.split_whitespace().collect();

        // Check for specific patterns
        if input_lower.contains("system info") || input_lower.contains("sysinfo")
            || input_lower.contains("uname")
        {
            return Self::SystemInfo;
        }

        if input_lower.contains("hostname") || input_lower.contains("host name") {
            return Self::Hostname;
        }

        if input_lower.contains("uptime") || input_lower.contains("up time") {
            return Self::Uptime;
        }

        if input_lower.contains("process") || input_lower.contains("ps aux") {
            if input_lower.contains("top") || input_lower.contains("heavy")
                || input_lower.contains("most")
            {
                // Try to extract count
                let count = words.iter()
                    .filter_map(|w| w.parse::<usize>().ok())
                    .next()
                    .unwrap_or(10);
                return Self::TopProcesses { count };
            }
            return Self::ListProcesses;
        }

        if input_lower.contains("top") && !input_lower.contains("stop") {
            let count = words.iter()
                .filter_map(|w| w.parse::<usize>().ok())
                .next()
                .unwrap_or(10);
            return Self::TopProcesses { count };
        }

        if input_lower.contains("service") {
            if input_lower.contains("list") || input_lower.contains("all") {
                return Self::ListServices;
            }
            // Try to extract service name
            if let Some(idx) = words.iter().position(|&w| w == "service" || w == "status") {
                if let Some(service) = words.get(idx + 1) {
                    return Self::ServiceStatus {
                        service: service.to_string()
                    };
                }
            }
            // Look for common service names
            for word in &words {
                if ["nginx", "apache", "mysql", "postgresql", "redis", "docker",
                    "ssh", "sshd", "systemd", "cron", "cups"].contains(word)
                {
                    return Self::ServiceStatus {
                        service: word.to_string()
                    };
                }
            }
            return Self::ListServices;
        }

        if input_lower.contains("disk") || input_lower.contains("storage")
            || input_lower.contains("df")
        {
            return Self::DiskUsage;
        }

        if input_lower.contains("memory") || input_lower.contains("mem")
            || input_lower.contains("ram") || input_lower.contains("free")
        {
            return Self::MemoryUsage;
        }

        if input_lower.contains("cpu") || input_lower.contains("processor") {
            return Self::CpuInfo;
        }

        if input_lower.contains("load") {
            return Self::LoadAverage;
        }

        Self::Unknown(input.to_string())
    }
}

/// System agent for system information and management
pub struct SystemAgent {
    capabilities: Vec<AgentCapability>,
}

impl SystemAgent {
    /// Create a new system agent
    pub fn new() -> Self {
        Self {
            capabilities: vec![
                AgentCapability::Execute,
                AgentCapability::ServiceManage,
                AgentCapability::Custom("system-info".to_string()),
            ],
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

    /// Get system information
    fn get_system_info(&self) -> AgentResponse {
        let mut result = String::new();
        let mut commands = Vec::new();

        // uname -a
        commands.push("uname -a".to_string());
        match self.execute_command("uname", &["-a"]) {
            Ok(output) => {
                result.push_str("System: ");
                result.push_str(output.trim());
                result.push('\n');
            }
            Err(e) => {
                result.push_str(&format!("System info error: {}\n", e));
            }
        }

        // hostname
        commands.push("hostname".to_string());
        match self.execute_command("hostname", &[]) {
            Ok(output) => {
                result.push_str("Hostname: ");
                result.push_str(output.trim());
                result.push('\n');
            }
            Err(_) => {}
        }

        // uptime
        commands.push("uptime".to_string());
        match self.execute_command("uptime", &[]) {
            Ok(output) => {
                result.push_str("Uptime: ");
                result.push_str(output.trim());
                result.push('\n');
            }
            Err(_) => {}
        }

        AgentResponse::success(result)
            .with_commands(commands)
            .with_suggestions(vec![
                "show disk usage".to_string(),
                "show memory usage".to_string(),
                "list services".to_string(),
            ])
    }

    /// Get hostname
    fn get_hostname(&self) -> AgentResponse {
        match self.execute_command("hostname", &[]) {
            Ok(output) => AgentResponse::success(output.trim().to_string())
                .with_commands(vec!["hostname".to_string()]),
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Get uptime
    fn get_uptime(&self) -> AgentResponse {
        match self.execute_command("uptime", &[]) {
            Ok(output) => AgentResponse::success(output.trim().to_string())
                .with_commands(vec!["uptime".to_string()]),
            Err(e) => AgentResponse::error(e),
        }
    }

    /// List all processes
    fn list_processes(&self) -> AgentResponse {
        // Try ps aux first, fall back to ps -ef
        match self.execute_command("ps", &["aux"]) {
            Ok(output) => AgentResponse::success(output)
                .with_commands(vec!["ps aux".to_string()])
                .with_suggestions(vec![
                    "show top 10 processes".to_string(),
                    "find process using port 8080".to_string(),
                ]),
            Err(_) => match self.execute_command("ps", &["-ef"]) {
                Ok(output) => AgentResponse::success(output)
                    .with_commands(vec!["ps -ef".to_string()]),
                Err(e) => AgentResponse::error(e),
            },
        }
    }

    /// Get top processes by resource usage
    fn top_processes(&self, count: usize) -> AgentResponse {
        // Use ps with sorting - cross-platform approach
        let count_str = count.to_string();

        // Try to get top processes by CPU
        let cmd = format!("ps aux --sort=-%cpu | head -n {}", count + 1);
        match self.execute_command("sh", &["-c", &cmd]) {
            Ok(output) => AgentResponse::success(output)
                .with_commands(vec![cmd])
                .with_suggestions(vec![
                    "show disk usage".to_string(),
                    "show memory usage".to_string(),
                ]),
            Err(_) => {
                // macOS fallback
                let cmd = format!("ps aux | head -n {}", count + 1);
                match self.execute_command("sh", &["-c", &cmd]) {
                    Ok(output) => AgentResponse::success(output)
                        .with_commands(vec![cmd]),
                    Err(e) => AgentResponse::error(e),
                }
            }
        }
    }

    /// Check service status
    fn service_status(&self, service: &str) -> AgentResponse {
        // Try systemctl first (Linux)
        let systemctl_result = self.execute_command("systemctl", &["status", service]);
        if let Ok(output) = systemctl_result {
            return AgentResponse::success(output)
                .with_commands(vec![format!("systemctl status {}", service)])
                .with_suggestions(vec![
                    format!("restart service {}", service),
                    format!("stop service {}", service),
                    "list services".to_string(),
                ]);
        }

        // Try launchctl on macOS
        let launchctl_result = self.execute_command("launchctl", &["list"]);
        if let Ok(output) = launchctl_result {
            // Filter for the service
            let filtered: String = output
                .lines()
                .filter(|line| line.to_lowercase().contains(&service.to_lowercase()))
                .collect::<Vec<_>>()
                .join("\n");

            if !filtered.is_empty() {
                return AgentResponse::success(filtered)
                    .with_commands(vec![format!("launchctl list | grep {}", service)]);
            }
        }

        // Try service command (older systems)
        match self.execute_command("service", &[service, "status"]) {
            Ok(output) => AgentResponse::success(output)
                .with_commands(vec![format!("service {} status", service)]),
            Err(e) => AgentResponse::error(format!("Could not get status for {}: {}", service, e)),
        }
    }

    /// List services
    fn list_services(&self) -> AgentResponse {
        // Try systemctl first (Linux)
        let cmd = "systemctl list-units --type=service --state=running";
        if let Ok(output) = self.execute_command("sh", &["-c", cmd]) {
            return AgentResponse::success(output)
                .with_commands(vec![cmd.to_string()])
                .with_suggestions(vec![
                    "check service nginx".to_string(),
                    "check service docker".to_string(),
                ]);
        }

        // Try launchctl on macOS
        match self.execute_command("launchctl", &["list"]) {
            Ok(output) => AgentResponse::success(output)
                .with_commands(vec!["launchctl list".to_string()]),
            Err(e) => AgentResponse::error(format!("Could not list services: {}", e)),
        }
    }

    /// Get disk usage
    fn disk_usage(&self) -> AgentResponse {
        match self.execute_command("df", &["-h"]) {
            Ok(output) => AgentResponse::success(output)
                .with_commands(vec!["df -h".to_string()])
                .with_suggestions(vec![
                    "find large files".to_string(),
                    "show memory usage".to_string(),
                ]),
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Get memory usage
    fn memory_usage(&self) -> AgentResponse {
        // Try free first (Linux)
        if let Ok(output) = self.execute_command("free", &["-h"]) {
            return AgentResponse::success(output)
                .with_commands(vec!["free -h".to_string()])
                .with_suggestions(vec![
                    "show disk usage".to_string(),
                    "show top processes".to_string(),
                ]);
        }

        // macOS fallback - use vm_stat
        if let Ok(output) = self.execute_command("vm_stat", &[]) {
            return AgentResponse::success(output)
                .with_commands(vec!["vm_stat".to_string()]);
        }

        AgentResponse::error("Could not get memory usage".to_string())
    }

    /// Get CPU info
    fn cpu_info(&self) -> AgentResponse {
        // Try lscpu first (Linux)
        if let Ok(output) = self.execute_command("lscpu", &[]) {
            return AgentResponse::success(output)
                .with_commands(vec!["lscpu".to_string()]);
        }

        // Try /proc/cpuinfo
        if let Ok(output) = self.execute_command("sh", &["-c", "cat /proc/cpuinfo | head -n 30"]) {
            return AgentResponse::success(output)
                .with_commands(vec!["cat /proc/cpuinfo".to_string()]);
        }

        // macOS fallback
        if let Ok(output) = self.execute_command("sysctl", &["-n", "machdep.cpu.brand_string"]) {
            return AgentResponse::success(output)
                .with_commands(vec!["sysctl -n machdep.cpu.brand_string".to_string()]);
        }

        AgentResponse::error("Could not get CPU info".to_string())
    }

    /// Get load average
    fn load_average(&self) -> AgentResponse {
        match self.execute_command("uptime", &[]) {
            Ok(output) => {
                // Extract just the load average part
                if let Some(idx) = output.find("load average") {
                    let load_part = &output[idx..];
                    return AgentResponse::success(load_part.to_string())
                        .with_commands(vec!["uptime".to_string()]);
                }
                AgentResponse::success(output)
                    .with_commands(vec!["uptime".to_string()])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Handle unknown command - try to execute it
    fn handle_unknown(&self, command: &str) -> AgentResponse {
        // For safety, we don't execute unknown commands directly
        // Instead, provide suggestions
        AgentResponse::error(format!("Unknown system command: {}", command))
            .with_suggestions(vec![
                "show system info".to_string(),
                "show disk usage".to_string(),
                "show memory usage".to_string(),
                "list processes".to_string(),
                "list services".to_string(),
            ])
    }
}

impl Default for SystemAgent {
    fn default() -> Self {
        Self::new()
    }
}

impl Agent for SystemAgent {
    fn name(&self) -> &str {
        "system"
    }

    fn description(&self) -> &str {
        "System information, services, and configuration"
    }

    fn capabilities(&self) -> &[AgentCapability] {
        &self.capabilities
    }

    fn can_handle(&self, request: &AgentRequest) -> bool {
        // Handle if explicitly targeted at system agent
        if request.agent == "system" || request.agent == "sys" {
            return true;
        }

        // Check if the command matches system-related keywords
        let cmd_lower = request.command.to_lowercase();
        cmd_lower.contains("system")
            || cmd_lower.contains("uname")
            || cmd_lower.contains("hostname")
            || cmd_lower.contains("uptime")
            || cmd_lower.contains("service")
            || cmd_lower.contains("disk")
            || cmd_lower.contains("memory")
            || cmd_lower.contains("ram")
            || cmd_lower.contains("cpu")
            || cmd_lower.contains("load")
            || cmd_lower.contains("df ")
            || cmd_lower.contains("free")
    }

    fn handle(&self, request: AgentRequest) -> AgentResponse {
        let command = SystemCommand::parse(&request.command);

        match command {
            SystemCommand::SystemInfo => self.get_system_info(),
            SystemCommand::Hostname => self.get_hostname(),
            SystemCommand::Uptime => self.get_uptime(),
            SystemCommand::ListProcesses => self.list_processes(),
            SystemCommand::TopProcesses { count } => self.top_processes(count),
            SystemCommand::ServiceStatus { service } => self.service_status(&service),
            SystemCommand::ListServices => self.list_services(),
            SystemCommand::DiskUsage => self.disk_usage(),
            SystemCommand::MemoryUsage => self.memory_usage(),
            SystemCommand::CpuInfo => self.cpu_info(),
            SystemCommand::LoadAverage => self.load_average(),
            SystemCommand::Unknown(cmd) => self.handle_unknown(&cmd),
        }
    }

    fn examples(&self) -> &[&str] {
        &[
            "show system info",
            "list running services",
            "check disk usage",
            "show memory usage",
            "check service nginx",
            "show top 10 processes",
            "get hostname",
            "show uptime",
        ]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_system_info() {
        assert_eq!(SystemCommand::parse("show system info"), SystemCommand::SystemInfo);
        assert_eq!(SystemCommand::parse("sysinfo"), SystemCommand::SystemInfo);
        assert_eq!(SystemCommand::parse("uname -a"), SystemCommand::SystemInfo);
    }

    #[test]
    fn test_parse_disk_usage() {
        assert_eq!(SystemCommand::parse("show disk usage"), SystemCommand::DiskUsage);
        assert_eq!(SystemCommand::parse("disk space"), SystemCommand::DiskUsage);
        assert_eq!(SystemCommand::parse("df -h"), SystemCommand::DiskUsage);
    }

    #[test]
    fn test_parse_memory() {
        assert_eq!(SystemCommand::parse("show memory"), SystemCommand::MemoryUsage);
        assert_eq!(SystemCommand::parse("ram usage"), SystemCommand::MemoryUsage);
        assert_eq!(SystemCommand::parse("free -h"), SystemCommand::MemoryUsage);
    }

    #[test]
    fn test_parse_service_status() {
        assert!(matches!(
            SystemCommand::parse("check service nginx"),
            SystemCommand::ServiceStatus { service } if service == "nginx"
        ));
    }

    #[test]
    fn test_parse_top_processes() {
        assert!(matches!(
            SystemCommand::parse("top 5 processes"),
            SystemCommand::TopProcesses { count: 5 }
        ));
    }

    #[test]
    fn test_agent_can_handle() {
        let agent = SystemAgent::new();

        let req = AgentRequest::new("system", "show disk usage");
        assert!(agent.can_handle(&req));

        let req = AgentRequest::new("other", "show memory");
        assert!(agent.can_handle(&req));

        let req = AgentRequest::new("other", "random stuff");
        assert!(!agent.can_handle(&req));
    }
}
