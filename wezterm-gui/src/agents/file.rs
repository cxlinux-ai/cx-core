//! File Agent - File system operations
//!
//! Provides capabilities for:
//! - Searching files (find, fd)
//! - Reading file contents
//! - Listing directories
//! - Getting file info (stat)
//! - Searching in files (grep, rg)

use super::traits::{Agent, AgentCapability, AgentRequest, AgentResponse};
use std::path::Path;
use std::process::Command;

/// Expand tilde in paths to home directory
fn expand_tilde(path: &str) -> String {
    if path.starts_with("~/") {
        if let Some(home) = dirs_next::home_dir() {
            return home.join(&path[2..]).to_string_lossy().to_string();
        }
    } else if path == "~" {
        if let Some(home) = dirs_next::home_dir() {
            return home.to_string_lossy().to_string();
        }
    }
    path.to_string()
}

/// Commands that the file agent can handle
#[derive(Debug, Clone, PartialEq)]
pub enum FileCommand {
    /// List directory contents
    ListDirectory { path: String },
    /// Read file contents
    ReadFile { path: String, lines: Option<usize> },
    /// Get file/directory info
    FileInfo { path: String },
    /// Find files by name pattern
    FindFiles { pattern: String, path: Option<String> },
    /// Find large files
    FindLargeFiles { size: String, path: Option<String> },
    /// Find recent files
    FindRecentFiles { days: usize, path: Option<String> },
    /// Search in files (grep)
    SearchInFiles { pattern: String, path: Option<String>, file_pattern: Option<String> },
    /// Get directory size
    DirectorySize { path: String },
    /// Count files
    CountFiles { path: String, pattern: Option<String> },
    /// Unknown command
    Unknown(String),
}

impl FileCommand {
    /// Parse a command string into a FileCommand
    pub fn parse(input: &str) -> Self {
        let input_lower = input.to_lowercase();
        let words: Vec<&str> = input.split_whitespace().collect();

        // List directory
        if input_lower.starts_with("ls") || input_lower.starts_with("list")
            || input_lower.contains("list dir") || input_lower.contains("show files")
        {
            let path = Self::extract_path(&words).unwrap_or(".".to_string());
            return Self::ListDirectory { path };
        }

        // Read file
        if input_lower.starts_with("cat") || input_lower.starts_with("read")
            || input_lower.contains("show file") || input_lower.contains("view file")
        {
            if let Some(path) = Self::extract_path(&words) {
                // Check for line limit
                let lines = words.iter()
                    .position(|&w| w == "-n" || w == "--lines")
                    .and_then(|i| words.get(i + 1))
                    .and_then(|s| s.parse().ok());
                return Self::ReadFile { path, lines };
            }
        }

        // File info (stat)
        if input_lower.contains("info") || input_lower.contains("stat")
            || input_lower.contains("details")
        {
            if let Some(path) = Self::extract_path(&words) {
                return Self::FileInfo { path };
            }
        }

        // Find large files
        if (input_lower.contains("large") || input_lower.contains("big"))
            && input_lower.contains("file")
        {
            // Try to extract size (e.g., "100M", "1G")
            let size = words.iter()
                .find(|w| w.ends_with('M') || w.ends_with('G') || w.ends_with('K'))
                .map(|s| s.to_string())
                .unwrap_or("100M".to_string());
            let path = Self::extract_path(&words);
            return Self::FindLargeFiles { size, path };
        }

        // Find recent files
        if input_lower.contains("recent") || input_lower.contains("new file")
            || input_lower.contains("modified")
        {
            let days = words.iter()
                .filter_map(|w| w.parse::<usize>().ok())
                .next()
                .unwrap_or(7);
            let path = Self::extract_path(&words);
            return Self::FindRecentFiles { days, path };
        }

        // Find files by pattern
        if input_lower.contains("find") || input_lower.contains("search for")
            || input_lower.contains("locate")
        {
            // Look for pattern (often in quotes or with *)
            let pattern = words.iter()
                .find(|w| w.contains('*') || w.contains('.'))
                .map(|s| s.trim_matches('"').trim_matches('\'').to_string())
                .unwrap_or("*".to_string());
            let path = Self::extract_path(&words);
            return Self::FindFiles { pattern, path };
        }

        // Grep/search in files
        if input_lower.contains("grep") || input_lower.contains("search in")
            || input_lower.contains("find text") || input_lower.contains("search for")
        {
            // Extract pattern (usually quoted or after specific keywords)
            let pattern = Self::extract_quoted(&input)
                .or_else(|| {
                    words.iter()
                        .skip_while(|&w| w.to_lowercase() != "for" && w.to_lowercase() != "grep")
                        .nth(1)
                        .map(|s| s.to_string())
                })
                .unwrap_or_default();

            let path = Self::extract_path(&words);
            let file_pattern = words.iter()
                .find(|w| w.contains('*') && w.contains('.'))
                .map(|s| s.to_string());

            return Self::SearchInFiles { pattern, path, file_pattern };
        }

        // Directory size
        if input_lower.contains("size") && (input_lower.contains("dir") || input_lower.contains("folder")) {
            let path = Self::extract_path(&words).unwrap_or(".".to_string());
            return Self::DirectorySize { path };
        }

        // Count files
        if input_lower.contains("count") && input_lower.contains("file") {
            let path = Self::extract_path(&words).unwrap_or(".".to_string());
            let pattern = words.iter()
                .find(|w| w.contains('*'))
                .map(|s| s.to_string());
            return Self::CountFiles { path, pattern };
        }

        Self::Unknown(input.to_string())
    }

    /// Extract a path from the command words
    fn extract_path(words: &[&str]) -> Option<String> {
        words.iter()
            .find(|w| {
                w.starts_with('/') || w.starts_with('.') || w.starts_with('~')
                    || w.contains('/')
            })
            .map(|s| s.to_string())
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
}

/// File agent for file system operations
pub struct FileAgent {
    capabilities: Vec<AgentCapability>,
}

impl FileAgent {
    /// Create a new file agent
    pub fn new() -> Self {
        Self {
            capabilities: vec![
                AgentCapability::ReadFile,
                AgentCapability::Execute,
                AgentCapability::Custom("file-search".to_string()),
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

    /// List directory contents
    fn list_directory(&self, path: &str) -> AgentResponse {
        let expanded_path = expand_tilde(path);

        // Try exa/eza first (modern ls)
        if let Ok(output) = self.execute_command("eza", &["-la", "--icons", &expanded_path]) {
            return AgentResponse::success(output)
                .with_commands(vec![format!("eza -la --icons {}", path)])
                .with_suggestions(vec![
                    format!("show directory size {}", path),
                    format!("find large files in {}", path),
                ]);
        }

        // Fall back to ls
        match self.execute_command("ls", &["-la", &expanded_path]) {
            Ok(output) => AgentResponse::success(output)
                .with_commands(vec![format!("ls -la {}", path)])
                .with_suggestions(vec![
                    format!("show directory size {}", path),
                ]),
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Read file contents
    fn read_file(&self, path: &str, lines: Option<usize>) -> AgentResponse {
        let expanded_path = expand_tilde(path);

        // Check if file exists
        if !Path::new(&expanded_path).exists() {
            return AgentResponse::error(format!("File not found: {}", path));
        }

        // Try bat first (syntax highlighting)
        if let Some(limit) = lines {
            let limit_str = limit.to_string();
            if let Ok(output) = self.execute_command("bat", &["--plain", "-n", "--line-range", &format!(":{}",limit_str), &expanded_path]) {
                return AgentResponse::success(output)
                    .with_commands(vec![format!("bat --plain -n --line-range :{} {}", limit, path)]);
            }
            // Fall back to head
            if let Ok(output) = self.execute_command("head", &["-n", &limit_str, &expanded_path]) {
                return AgentResponse::success(output)
                    .with_commands(vec![format!("head -n {} {}", limit, path)]);
            }
        } else {
            if let Ok(output) = self.execute_command("bat", &["--plain", "-n", &expanded_path]) {
                return AgentResponse::success(output)
                    .with_commands(vec![format!("bat --plain -n {}", path)]);
            }
        }

        // Fall back to cat
        match self.execute_command("cat", &[&expanded_path]) {
            Ok(output) => AgentResponse::success(output)
                .with_commands(vec![format!("cat {}", path)]),
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Get file info
    fn file_info(&self, path: &str) -> AgentResponse {
        let expanded_path = expand_tilde(path);

        // Try stat (cross-platform)
        #[cfg(target_os = "macos")]
        let stat_args = ["-x", &expanded_path];
        #[cfg(not(target_os = "macos"))]
        let stat_args = [&expanded_path as &str];

        match self.execute_command("stat", &stat_args) {
            Ok(output) => AgentResponse::success(output)
                .with_commands(vec![format!("stat {}", path)])
                .with_suggestions(vec![
                    format!("read file {}", path),
                ]),
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Find files by pattern
    fn find_files(&self, pattern: &str, path: Option<&str>) -> AgentResponse {
        let search_path = path.unwrap_or(".");
        let expanded_path = expand_tilde(search_path);

        // Try fd first (faster, more intuitive)
        if let Ok(output) = self.execute_command("fd", &[pattern, &expanded_path]) {
            return AgentResponse::success(output)
                .with_commands(vec![format!("fd {} {}", pattern, search_path)])
                .with_suggestions(vec![
                    format!("search in files for pattern {}", pattern),
                ]);
        }

        // Fall back to find
        match self.execute_command("find", &[&expanded_path, "-name", pattern]) {
            Ok(output) => AgentResponse::success(output)
                .with_commands(vec![format!("find {} -name {}", search_path, pattern)]),
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Find large files
    fn find_large_files(&self, size: &str, path: Option<&str>) -> AgentResponse {
        let search_path = path.unwrap_or(".");
        let expanded_path = expand_tilde(search_path);

        // Try fd with size filter
        if let Ok(output) = self.execute_command("fd", &[".", &expanded_path, "-S", &format!("+{}", size), "-t", "f"]) {
            return AgentResponse::success(output)
                .with_commands(vec![format!("fd . {} -S +{} -t f", search_path, size)])
                .with_suggestions(vec![
                    "show disk usage".to_string(),
                ]);
        }

        // Fall back to find
        match self.execute_command("find", &[&expanded_path, "-type", "f", "-size", &format!("+{}", size)]) {
            Ok(output) => AgentResponse::success(output)
                .with_commands(vec![format!("find {} -type f -size +{}", search_path, size)]),
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Find recently modified files
    fn find_recent_files(&self, days: usize, path: Option<&str>) -> AgentResponse {
        let search_path = path.unwrap_or(".");
        let expanded_path = expand_tilde(search_path);
        let days_str = days.to_string();

        // Try fd with time filter
        if let Ok(output) = self.execute_command("fd", &[".", &expanded_path, "--changed-within", &format!("{}d", days), "-t", "f"]) {
            return AgentResponse::success(output)
                .with_commands(vec![format!("fd . {} --changed-within {}d -t f", search_path, days)]);
        }

        // Fall back to find
        match self.execute_command("find", &[&expanded_path, "-type", "f", "-mtime", &format!("-{}", days_str)]) {
            Ok(output) => AgentResponse::success(output)
                .with_commands(vec![format!("find {} -type f -mtime -{}", search_path, days)]),
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Search in files (grep)
    fn search_in_files(&self, pattern: &str, path: Option<&str>, file_pattern: Option<&str>) -> AgentResponse {
        let search_path = path.unwrap_or(".");
        let expanded_path = expand_tilde(search_path);

        // Try ripgrep first
        let mut rg_args = vec![pattern, &expanded_path];
        if let Some(fp) = file_pattern {
            rg_args.extend(&["-g", fp]);
        }

        if let Ok(output) = self.execute_command("rg", &rg_args) {
            let cmd = if let Some(fp) = file_pattern {
                format!("rg {} {} -g {}", pattern, search_path, fp)
            } else {
                format!("rg {} {}", pattern, search_path)
            };
            return AgentResponse::success(output)
                .with_commands(vec![cmd]);
        }

        // Fall back to grep
        let mut grep_args = vec!["-r", pattern, &expanded_path];
        if let Some(fp) = file_pattern {
            grep_args.extend(&["--include", fp]);
        }

        match self.execute_command("grep", &grep_args) {
            Ok(output) => {
                let cmd = if let Some(fp) = file_pattern {
                    format!("grep -r {} {} --include {}", pattern, search_path, fp)
                } else {
                    format!("grep -r {} {}", pattern, search_path)
                };
                AgentResponse::success(output).with_commands(vec![cmd])
            }
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Get directory size
    fn directory_size(&self, path: &str) -> AgentResponse {
        let expanded_path = expand_tilde(path);

        // Try dust (modern du)
        if let Ok(output) = self.execute_command("dust", &["-d", "1", &expanded_path]) {
            return AgentResponse::success(output)
                .with_commands(vec![format!("dust -d 1 {}", path)]);
        }

        // Fall back to du
        match self.execute_command("du", &["-sh", &expanded_path]) {
            Ok(output) => AgentResponse::success(output)
                .with_commands(vec![format!("du -sh {}", path)])
                .with_suggestions(vec![
                    format!("list directory {}", path),
                    format!("find large files in {}", path),
                ]),
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Count files
    fn count_files(&self, path: &str, pattern: Option<&str>) -> AgentResponse {
        let expanded_path = expand_tilde(path);

        let cmd = if let Some(pat) = pattern {
            format!("find {} -name '{}' -type f | wc -l", path, pat)
        } else {
            format!("find {} -type f | wc -l", path)
        };

        match self.execute_command("sh", &["-c", &cmd]) {
            Ok(output) => AgentResponse::success(format!("File count: {}", output.trim()))
                .with_commands(vec![cmd]),
            Err(e) => AgentResponse::error(e),
        }
    }

    /// Handle unknown command
    fn handle_unknown(&self, command: &str) -> AgentResponse {
        AgentResponse::error(format!("Unknown file command: {}", command))
            .with_suggestions(vec![
                "list directory .".to_string(),
                "find *.log files".to_string(),
                "find large files".to_string(),
                "search in files for TODO".to_string(),
            ])
    }
}

impl Default for FileAgent {
    fn default() -> Self {
        Self::new()
    }
}

impl Agent for FileAgent {
    fn name(&self) -> &str {
        "file"
    }

    fn description(&self) -> &str {
        "File and directory operations"
    }

    fn capabilities(&self) -> &[AgentCapability] {
        &self.capabilities
    }

    fn can_handle(&self, request: &AgentRequest) -> bool {
        // Handle if explicitly targeted at file agent
        if request.agent == "file" || request.agent == "files" || request.agent == "fs" {
            return true;
        }

        // Check if the command matches file-related keywords
        let cmd_lower = request.command.to_lowercase();
        cmd_lower.contains("file")
            || cmd_lower.contains("directory")
            || cmd_lower.contains("folder")
            || cmd_lower.contains("find")
            || cmd_lower.contains("search")
            || cmd_lower.contains("grep")
            || cmd_lower.contains("ls ")
            || cmd_lower.starts_with("ls")
            || cmd_lower.contains("cat ")
            || cmd_lower.starts_with("cat")
            || cmd_lower.contains("read ")
            || cmd_lower.starts_with("read")
    }

    fn handle(&self, request: AgentRequest) -> AgentResponse {
        let command = FileCommand::parse(&request.command);

        match command {
            FileCommand::ListDirectory { path } => self.list_directory(&path),
            FileCommand::ReadFile { path, lines } => self.read_file(&path, lines),
            FileCommand::FileInfo { path } => self.file_info(&path),
            FileCommand::FindFiles { pattern, path } => self.find_files(&pattern, path.as_deref()),
            FileCommand::FindLargeFiles { size, path } => self.find_large_files(&size, path.as_deref()),
            FileCommand::FindRecentFiles { days, path } => self.find_recent_files(days, path.as_deref()),
            FileCommand::SearchInFiles { pattern, path, file_pattern } => {
                self.search_in_files(&pattern, path.as_deref(), file_pattern.as_deref())
            }
            FileCommand::DirectorySize { path } => self.directory_size(&path),
            FileCommand::CountFiles { path, pattern } => self.count_files(&path, pattern.as_deref()),
            FileCommand::Unknown(cmd) => self.handle_unknown(&cmd),
        }
    }

    fn examples(&self) -> &[&str] {
        &[
            "list directory /home",
            "find *.log files",
            "find large files over 100M",
            "find recent files from last 7 days",
            "search for TODO in files",
            "show directory size .",
            "read file /etc/hosts",
            "file info ~/.bashrc",
        ]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_list_directory() {
        assert!(matches!(
            FileCommand::parse("ls /home"),
            FileCommand::ListDirectory { path } if path == "/home"
        ));
        assert!(matches!(
            FileCommand::parse("list directory /tmp"),
            FileCommand::ListDirectory { path } if path == "/tmp"
        ));
    }

    #[test]
    fn test_parse_find_files() {
        assert!(matches!(
            FileCommand::parse("find *.log"),
            FileCommand::FindFiles { pattern, path: None } if pattern == "*.log"
        ));
    }

    #[test]
    fn test_parse_find_large_files() {
        assert!(matches!(
            FileCommand::parse("find large files over 100M"),
            FileCommand::FindLargeFiles { size, path: None } if size == "100M"
        ));
    }

    #[test]
    fn test_agent_can_handle() {
        let agent = FileAgent::new();

        let req = AgentRequest::new("file", "list directory");
        assert!(agent.can_handle(&req));

        let req = AgentRequest::new("other", "find *.log files");
        assert!(agent.can_handle(&req));
    }
}
