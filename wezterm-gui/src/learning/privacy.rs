//! Privacy Filter
//!
//! Filters sensitive data from collected learning data.

use regex::Regex;
use std::collections::HashSet;

extern crate gethostname;

/// Privacy configuration
#[derive(Debug, Clone)]
pub struct PrivacyConfig {
    /// Filter passwords from commands
    pub filter_passwords: bool,

    /// Filter API keys and tokens
    pub filter_tokens: bool,

    /// Filter SSH keys
    pub filter_ssh_keys: bool,

    /// Filter file paths containing sensitive directories
    pub filter_sensitive_paths: bool,

    /// Filter IP addresses
    pub filter_ip_addresses: bool,

    /// Filter email addresses
    pub filter_emails: bool,

    /// Anonymize usernames
    pub anonymize_usernames: bool,

    /// Anonymize hostnames
    pub anonymize_hostnames: bool,

    /// Custom patterns to filter
    pub custom_patterns: Vec<String>,

    /// Directories considered sensitive
    pub sensitive_dirs: Vec<String>,
}

impl Default for PrivacyConfig {
    fn default() -> Self {
        Self {
            filter_passwords: true,
            filter_tokens: true,
            filter_ssh_keys: true,
            filter_sensitive_paths: true,
            filter_ip_addresses: false, // Off by default
            filter_emails: false,       // Off by default
            anonymize_usernames: false,
            anonymize_hostnames: false,
            custom_patterns: Vec::new(),
            sensitive_dirs: vec![
                ".ssh".to_string(),
                ".gnupg".to_string(),
                ".aws".to_string(),
                ".config/gcloud".to_string(),
                ".kube".to_string(),
                "credentials".to_string(),
                "secrets".to_string(),
            ],
        }
    }
}

/// Sensitive pattern definition
#[derive(Debug, Clone)]
pub struct SensitivePattern {
    /// Pattern name
    pub name: String,

    /// Regex pattern
    pub pattern: Regex,

    /// Replacement text
    pub replacement: String,

    /// Whether this pattern is enabled
    pub enabled: bool,
}

impl SensitivePattern {
    pub fn new(name: &str, pattern: &str, replacement: &str) -> Option<Self> {
        Regex::new(pattern).ok().map(|regex| Self {
            name: name.to_string(),
            pattern: regex,
            replacement: replacement.to_string(),
            enabled: true,
        })
    }
}

/// Privacy filter for learning data
pub struct PrivacyFilter {
    /// Configuration
    config: PrivacyConfig,

    /// Compiled patterns
    patterns: Vec<SensitivePattern>,

    /// Known sensitive commands
    sensitive_commands: HashSet<String>,

    /// Known sensitive environment variables
    sensitive_env_vars: HashSet<String>,
}

impl PrivacyFilter {
    /// Create a new privacy filter
    pub fn new(config: PrivacyConfig) -> Self {
        let mut filter = Self {
            patterns: Vec::new(),
            sensitive_commands: HashSet::new(),
            sensitive_env_vars: HashSet::new(),
            config,
        };

        filter.compile_patterns();
        filter.init_sensitive_lists();

        filter
    }

    /// Compile regex patterns based on configuration
    fn compile_patterns(&mut self) {
        self.patterns.clear();

        // Password patterns
        if self.config.filter_passwords {
            if let Some(p) = SensitivePattern::new(
                "password_flag",
                r"(-p|--password|--passwd|PASSWORD=)\s*\S+",
                "$1 [FILTERED]",
            ) {
                self.patterns.push(p);
            }

            if let Some(p) = SensitivePattern::new(
                "password_env",
                r#"(?i)(password|passwd|pwd|secret)\s*=\s*['"]?[^'"\s]+['"]?"#,
                "$1=[FILTERED]",
            ) {
                self.patterns.push(p);
            }
        }

        // Token patterns
        if self.config.filter_tokens {
            // API keys (generic patterns)
            if let Some(p) = SensitivePattern::new(
                "api_key",
                r#"(?i)(api[_-]?key|apikey|api_token|access[_-]?token|auth[_-]?token|bearer)\s*[=:]\s*['"]?[A-Za-z0-9_-]{20,}['"]?"#,
                "$1=[FILTERED]",
            ) {
                self.patterns.push(p);
            }

            // AWS keys
            if let Some(p) = SensitivePattern::new(
                "aws_key",
                r"AKIA[0-9A-Z]{16}",
                "[AWS_KEY_FILTERED]",
            ) {
                self.patterns.push(p);
            }

            // GitHub tokens
            if let Some(p) = SensitivePattern::new(
                "github_token",
                r"gh[pousr]_[A-Za-z0-9_]{36,}",
                "[GITHUB_TOKEN_FILTERED]",
            ) {
                self.patterns.push(p);
            }

            // JWT tokens
            if let Some(p) = SensitivePattern::new(
                "jwt",
                r"eyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*",
                "[JWT_FILTERED]",
            ) {
                self.patterns.push(p);
            }

            // Generic long hex strings (likely tokens)
            if let Some(p) = SensitivePattern::new(
                "hex_token",
                r"\b[a-fA-F0-9]{32,}\b",
                "[TOKEN_FILTERED]",
            ) {
                self.patterns.push(p);
            }
        }

        // SSH key patterns
        if self.config.filter_ssh_keys {
            if let Some(p) = SensitivePattern::new(
                "ssh_private_key",
                r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----[\s\S]*?-----END (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
                "[SSH_KEY_FILTERED]",
            ) {
                self.patterns.push(p);
            }
        }

        // IP address patterns
        if self.config.filter_ip_addresses {
            if let Some(p) = SensitivePattern::new(
                "ipv4",
                r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b",
                "[IP_FILTERED]",
            ) {
                self.patterns.push(p);
            }
        }

        // Email patterns
        if self.config.filter_emails {
            if let Some(p) = SensitivePattern::new(
                "email",
                r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
                "[EMAIL_FILTERED]",
            ) {
                self.patterns.push(p);
            }
        }

        // Custom patterns
        for custom in &self.config.custom_patterns {
            if let Some(p) = SensitivePattern::new("custom", custom, "[FILTERED]") {
                self.patterns.push(p);
            }
        }
    }

    /// Initialize sensitive command and env var lists
    fn init_sensitive_lists(&mut self) {
        self.sensitive_commands = [
            "mysql",
            "psql",
            "mongo",
            "redis-cli",
            "ssh",
            "scp",
            "sftp",
            "curl",
            "wget",
            "htpasswd",
            "openssl",
            "gpg",
            "pass",
            "vault",
            "aws",
            "gcloud",
            "az",
            "kubectl",
        ]
        .iter()
        .map(|s| s.to_string())
        .collect();

        self.sensitive_env_vars = [
            "PASSWORD",
            "PASSWD",
            "SECRET",
            "TOKEN",
            "API_KEY",
            "APIKEY",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "GITHUB_TOKEN",
            "NPM_TOKEN",
            "DOCKER_PASSWORD",
            "DATABASE_URL",
            "MONGODB_URI",
            "REDIS_URL",
            "PRIVATE_KEY",
            "SSH_AUTH_SOCK",
        ]
        .iter()
        .map(|s| s.to_string())
        .collect();
    }

    /// Filter a command string
    pub fn filter_command(&self, command: &str) -> String {
        let mut filtered = command.to_string();

        // Check if command is sensitive
        let cmd_base = command.split_whitespace().next().unwrap_or("");
        let is_sensitive_cmd = self.sensitive_commands.contains(cmd_base);

        // Apply patterns
        for pattern in &self.patterns {
            if pattern.enabled {
                filtered = pattern
                    .pattern
                    .replace_all(&filtered, &pattern.replacement)
                    .to_string();
            }
        }

        // Filter sensitive paths
        if self.config.filter_sensitive_paths {
            filtered = self.filter_paths(&filtered);
        }

        // For sensitive commands, be more aggressive
        if is_sensitive_cmd {
            filtered = self.filter_sensitive_command(&filtered);
        }

        // Anonymize if configured
        if self.config.anonymize_usernames {
            filtered = self.anonymize_username(&filtered);
        }

        if self.config.anonymize_hostnames {
            filtered = self.anonymize_hostname(&filtered);
        }

        filtered
    }

    /// Filter output text
    pub fn filter_output(&self, output: &str) -> String {
        let mut filtered = output.to_string();

        // Apply all patterns
        for pattern in &self.patterns {
            if pattern.enabled {
                filtered = pattern
                    .pattern
                    .replace_all(&filtered, &pattern.replacement)
                    .to_string();
            }
        }

        // Truncate long outputs
        if filtered.len() > 1000 {
            filtered = format!("{}... [truncated]", &filtered[..1000]);
        }

        filtered
    }

    /// Filter paths containing sensitive directories
    fn filter_paths(&self, text: &str) -> String {
        let mut filtered = text.to_string();

        for dir in &self.config.sensitive_dirs {
            // Pattern to match paths containing sensitive directory
            if let Ok(re) = Regex::new(&format!(r"(/[^/\s]*)*/{}/[^\s]*", regex::escape(dir))) {
                filtered = re.replace_all(&filtered, "[SENSITIVE_PATH]").to_string();
            }
        }

        filtered
    }

    /// Additional filtering for sensitive commands
    fn filter_sensitive_command(&self, command: &str) -> String {
        let parts: Vec<&str> = command.split_whitespace().collect();
        if parts.is_empty() {
            return command.to_string();
        }

        let cmd = parts[0];
        let mut filtered_parts = vec![cmd.to_string()];

        // Keep flags, filter values
        let mut skip_next = false;
        for (i, part) in parts.iter().enumerate().skip(1) {
            if skip_next {
                filtered_parts.push("[FILTERED]".to_string());
                skip_next = false;
                continue;
            }

            if part.starts_with('-') {
                filtered_parts.push(part.to_string());
                // Check if this flag takes a value
                if *part == "-p"
                    || *part == "-u"
                    || *part == "-h"
                    || part.contains("password")
                    || part.contains("user")
                    || part.contains("host")
                    || part.contains("key")
                {
                    skip_next = true;
                }
            } else if part.contains('@') || part.contains(':') {
                // Connection strings
                filtered_parts.push("[FILTERED]".to_string());
            } else if i == parts.len() - 1 && !part.starts_with('-') {
                // Last argument often contains sensitive data for these commands
                filtered_parts.push("[FILTERED]".to_string());
            } else {
                filtered_parts.push(part.to_string());
            }
        }

        filtered_parts.join(" ")
    }

    /// Anonymize username in text
    fn anonymize_username(&self, text: &str) -> String {
        // Get current username
        if let Ok(user) = std::env::var("USER") {
            return text.replace(&user, "[USER]");
        }
        text.to_string()
    }

    /// Anonymize hostname in text
    fn anonymize_hostname(&self, text: &str) -> String {
        if let Ok(hostname) = gethostname::gethostname().into_string() {
            return text.replace(&hostname, "[HOST]");
        }
        text.to_string()
    }

    /// Check if a command should be completely skipped
    pub fn should_skip_command(&self, command: &str) -> bool {
        let cmd_lower = command.to_lowercase();

        // Skip commands that likely contain credentials
        if cmd_lower.contains("echo") && cmd_lower.contains("password") {
            return true;
        }

        if cmd_lower.contains("export") && self.sensitive_env_vars.iter().any(|v| cmd_lower.contains(&v.to_lowercase())) {
            return true;
        }

        // Skip login commands
        if cmd_lower.starts_with("login")
            || cmd_lower.starts_with("passwd")
            || cmd_lower.contains("--password")
        {
            return true;
        }

        false
    }

    /// Get configuration
    pub fn config(&self) -> &PrivacyConfig {
        &self.config
    }

    /// Update configuration
    pub fn set_config(&mut self, config: PrivacyConfig) {
        self.config = config;
        self.compile_patterns();
    }

    /// Add a custom pattern
    pub fn add_pattern(&mut self, name: &str, pattern: &str, replacement: &str) -> bool {
        if let Some(p) = SensitivePattern::new(name, pattern, replacement) {
            self.patterns.push(p);
            true
        } else {
            false
        }
    }

    /// Remove a custom pattern by name
    pub fn remove_pattern(&mut self, name: &str) -> bool {
        let before = self.patterns.len();
        self.patterns.retain(|p| p.name != name);
        self.patterns.len() < before
    }

    /// Enable/disable a pattern
    pub fn set_pattern_enabled(&mut self, name: &str, enabled: bool) -> bool {
        for pattern in &mut self.patterns {
            if pattern.name == name {
                pattern.enabled = enabled;
                return true;
            }
        }
        false
    }
}

impl Default for PrivacyFilter {
    fn default() -> Self {
        Self::new(PrivacyConfig::default())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_privacy_config_default() {
        let config = PrivacyConfig::default();
        assert!(config.filter_passwords);
        assert!(config.filter_tokens);
        assert!(!config.filter_ip_addresses);
    }

    #[test]
    fn test_filter_password() {
        let filter = PrivacyFilter::default();

        let cmd = "mysql -u root -p secret123";
        let filtered = filter.filter_command(cmd);
        assert!(!filtered.contains("secret123"));
    }

    #[test]
    fn test_filter_api_key() {
        let filter = PrivacyFilter::default();

        let cmd = "curl -H 'Authorization: Bearer sk_live_abcdefghijklmnopqrstuvwxyz123456'";
        let filtered = filter.filter_command(cmd);
        assert!(!filtered.contains("sk_live_abcdefghijklmnopqrstuvwxyz123456"));
    }

    #[test]
    fn test_filter_aws_key() {
        let filter = PrivacyFilter::default();

        let text = "AWS key: AKIAIOSFODNN7EXAMPLE";
        let filtered = filter.filter_output(text);
        assert!(!filtered.contains("AKIAIOSFODNN7EXAMPLE"));
        assert!(filtered.contains("AWS_KEY_FILTERED"));
    }

    #[test]
    fn test_filter_jwt() {
        let filter = PrivacyFilter::default();

        let text = "Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U";
        let filtered = filter.filter_output(text);
        assert!(filtered.contains("JWT_FILTERED"));
    }

    #[test]
    fn test_filter_sensitive_path() {
        let filter = PrivacyFilter::default();

        let cmd = "cat /home/user/.ssh/id_rsa";
        let filtered = filter.filter_command(cmd);
        assert!(filtered.contains("SENSITIVE_PATH"));
    }

    #[test]
    fn test_should_skip_command() {
        let filter = PrivacyFilter::default();

        assert!(filter.should_skip_command("echo $PASSWORD"));
        assert!(filter.should_skip_command("export AWS_SECRET_ACCESS_KEY=abc123"));
        assert!(!filter.should_skip_command("ls -la"));
    }

    #[test]
    fn test_custom_pattern() {
        let mut filter = PrivacyFilter::default();

        filter.add_pattern("custom", r"my-secret-\d+", "[CUSTOM_FILTERED]");

        let text = "Value: my-secret-12345";
        let filtered = filter.filter_output(text);
        assert!(filtered.contains("CUSTOM_FILTERED"));
    }
}
