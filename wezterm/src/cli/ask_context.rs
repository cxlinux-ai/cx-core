//! CX Terminal: Context detection for smart AI responses
//!
//! Detects current directory, project type, and environment.

use std::env;
use std::path::{Path, PathBuf};

/// Detected project context
#[derive(Debug, Clone, Default)]
pub struct ProjectContext {
    pub cwd: PathBuf,
    pub dir_name: String,
    pub project_type: Option<ProjectType>,
    pub is_git_repo: bool,
    pub has_uncommitted: bool,
}

/// Type of project detected
#[derive(Debug, Clone, PartialEq)]
pub enum ProjectType {
    Python,
    Node,
    Rust,
    Go,
    Docker,
    Unknown,
}

impl ProjectContext {
    /// Detect context from current directory
    pub fn detect() -> Self {
        let cwd = env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
        let dir_name = cwd
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("project")
            .to_string();

        let project_type = Self::detect_project_type(&cwd);
        let is_git_repo = cwd.join(".git").exists();
        let has_uncommitted = Self::check_git_status(&cwd);

        Self {
            cwd,
            dir_name,
            project_type,
            is_git_repo,
            has_uncommitted,
        }
    }

    fn detect_project_type(dir: &Path) -> Option<ProjectType> {
        if dir.join("pyproject.toml").exists() || dir.join("requirements.txt").exists() {
            Some(ProjectType::Python)
        } else if dir.join("package.json").exists() {
            Some(ProjectType::Node)
        } else if dir.join("Cargo.toml").exists() {
            Some(ProjectType::Rust)
        } else if dir.join("go.mod").exists() {
            Some(ProjectType::Go)
        } else if dir.join("Dockerfile").exists() || dir.join("docker-compose.yml").exists() {
            Some(ProjectType::Docker)
        } else {
            None
        }
    }

    fn check_git_status(dir: &Path) -> bool {
        if !dir.join(".git").exists() {
            return false;
        }

        std::process::Command::new("git")
            .args(["status", "--porcelain"])
            .current_dir(dir)
            .output()
            .map(|o| !o.stdout.is_empty())
            .unwrap_or(false)
    }

    /// Generate a smart name for snapshots based on context
    pub fn smart_snapshot_name(&self) -> String {
        let base = self.dir_name.replace(' ', "-").to_lowercase();
        let timestamp = chrono::Local::now().format("%m%d");
        format!("{}-{}", base, timestamp)
    }

    /// Get context string for AI prompts
    pub fn to_prompt_context(&self) -> String {
        let mut ctx = format!("Current directory: {}\n", self.cwd.display());

        if let Some(ref pt) = self.project_type {
            ctx.push_str(&format!("Project type: {:?}\n", pt));
        }

        if self.is_git_repo {
            ctx.push_str("Git repository: yes\n");
            if self.has_uncommitted {
                ctx.push_str("Has uncommitted changes: yes\n");
            }
        }

        ctx
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_context_detection() {
        let ctx = ProjectContext::detect();
        assert!(!ctx.dir_name.is_empty());
    }

    #[test]
    fn test_smart_name() {
        let ctx = ProjectContext {
            cwd: PathBuf::from("/tmp/my-project"),
            dir_name: "my-project".to_string(),
            project_type: None,
            is_git_repo: false,
            has_uncommitted: false,
        };
        let name = ctx.smart_snapshot_name();
        assert!(name.starts_with("my-project-"));
    }
}
