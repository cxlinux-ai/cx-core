//! CX Terminal: Smart pattern matching for AI commands
//!
//! Detects user intent and maps to CX commands.


/// Result of pattern matching
#[derive(Debug, Clone)]
pub struct PatternMatch {
    pub command: String,
    pub description: String,
    pub confidence: f32,
    pub needs_name: bool,
}

/// Pattern matcher for CX commands
pub struct PatternMatcher {
    patterns: Vec<Pattern>,
}

struct Pattern {
    keywords: Vec<&'static str>,
    command_template: &'static str,
    description: &'static str,
    needs_name: bool,
    priority: u8,
}

impl PatternMatcher {
    pub fn new() -> Self {
        Self {
            patterns: vec![
                // Project creation patterns
                Pattern {
                    keywords: vec!["create", "python", "project"],
                    command_template: "cx new python {name}",
                    description: "Create a Python project",
                    needs_name: true,
                    priority: 10,
                },
                Pattern {
                    keywords: vec!["create", "python"],
                    command_template: "cx new python {name}",
                    description: "Create a Python project",
                    needs_name: true,
                    priority: 8,
                },
                Pattern {
                    keywords: vec!["python", "project"],
                    command_template: "cx new python {name}",
                    description: "Create a Python project",
                    needs_name: true,
                    priority: 7,
                },
                Pattern {
                    keywords: vec!["setup", "python"],
                    command_template: "cx new python {name}",
                    description: "Set up a Python project",
                    needs_name: true,
                    priority: 8,
                },
                Pattern {
                    keywords: vec!["create", "react", "app"],
                    command_template: "cx new react {name}",
                    description: "Create a React app",
                    needs_name: true,
                    priority: 10,
                },
                Pattern {
                    keywords: vec!["create", "react"],
                    command_template: "cx new react {name}",
                    description: "Create a React app",
                    needs_name: true,
                    priority: 8,
                },
                Pattern {
                    keywords: vec!["react", "app"],
                    command_template: "cx new react {name}",
                    description: "Create a React app",
                    needs_name: true,
                    priority: 7,
                },
                Pattern {
                    keywords: vec!["create", "next", "app"],
                    command_template: "cx new nextjs {name}",
                    description: "Create a Next.js app",
                    needs_name: true,
                    priority: 10,
                },
                Pattern {
                    keywords: vec!["nextjs", "project"],
                    command_template: "cx new nextjs {name}",
                    description: "Create a Next.js app",
                    needs_name: true,
                    priority: 8,
                },
                Pattern {
                    keywords: vec!["create", "node", "project"],
                    command_template: "cx new node {name}",
                    description: "Create a Node.js project",
                    needs_name: true,
                    priority: 10,
                },
                Pattern {
                    keywords: vec!["node", "project"],
                    command_template: "cx new node {name}",
                    description: "Create a Node.js project",
                    needs_name: true,
                    priority: 7,
                },
                Pattern {
                    keywords: vec!["create", "api", "backend"],
                    command_template: "cx new fastapi {name}",
                    description: "Create a FastAPI backend",
                    needs_name: true,
                    priority: 10,
                },
                Pattern {
                    keywords: vec!["fastapi", "project"],
                    command_template: "cx new fastapi {name}",
                    description: "Create a FastAPI project",
                    needs_name: true,
                    priority: 9,
                },
                Pattern {
                    keywords: vec!["create", "api"],
                    command_template: "cx new fastapi {name}",
                    description: "Create an API project",
                    needs_name: true,
                    priority: 7,
                },
                Pattern {
                    keywords: vec!["create", "express"],
                    command_template: "cx new express {name}",
                    description: "Create an Express.js backend",
                    needs_name: true,
                    priority: 9,
                },
                Pattern {
                    keywords: vec!["create", "docker"],
                    command_template: "cx new docker {name}",
                    description: "Create a Docker project",
                    needs_name: true,
                    priority: 9,
                },
                Pattern {
                    keywords: vec!["dockerize"],
                    command_template: "cx new docker {name}",
                    description: "Create Docker configuration",
                    needs_name: true,
                    priority: 8,
                },
                Pattern {
                    keywords: vec!["create", "go", "project"],
                    command_template: "cx new go {name}",
                    description: "Create a Go project",
                    needs_name: true,
                    priority: 10,
                },
                Pattern {
                    keywords: vec!["golang", "project"],
                    command_template: "cx new go {name}",
                    description: "Create a Go project",
                    needs_name: true,
                    priority: 8,
                },
                Pattern {
                    keywords: vec!["create", "rust", "project"],
                    command_template: "cx new rust {name}",
                    description: "Create a Rust project",
                    needs_name: true,
                    priority: 10,
                },
                Pattern {
                    keywords: vec!["rust", "project"],
                    command_template: "cx new rust {name}",
                    description: "Create a Rust project",
                    needs_name: true,
                    priority: 8,
                },
                Pattern {
                    keywords: vec!["create", "database"],
                    command_template: "cx new db {name}",
                    description: "Create a database project",
                    needs_name: true,
                    priority: 8,
                },
                Pattern {
                    keywords: vec!["sqlite", "project"],
                    command_template: "cx new db {name}",
                    description: "Create a SQLite project",
                    needs_name: true,
                    priority: 9,
                },
                // Snapshot patterns
                Pattern {
                    keywords: vec!["save", "work"],
                    command_template: "cx save {name}",
                    description: "Save workspace snapshot",
                    needs_name: true,
                    priority: 9,
                },
                Pattern {
                    keywords: vec!["save", "project"],
                    command_template: "cx save {name}",
                    description: "Save project snapshot",
                    needs_name: true,
                    priority: 9,
                },
                Pattern {
                    keywords: vec!["snapshot"],
                    command_template: "cx save {name}",
                    description: "Create a snapshot",
                    needs_name: true,
                    priority: 7,
                },
                Pattern {
                    keywords: vec!["backup"],
                    command_template: "cx save {name}",
                    description: "Backup current directory",
                    needs_name: true,
                    priority: 7,
                },
                Pattern {
                    keywords: vec!["list", "snapshots"],
                    command_template: "cx snapshots -l",
                    description: "List all snapshots",
                    needs_name: false,
                    priority: 10,
                },
                Pattern {
                    keywords: vec!["show", "snapshots"],
                    command_template: "cx snapshots -l",
                    description: "Show all snapshots",
                    needs_name: false,
                    priority: 9,
                },
                Pattern {
                    keywords: vec!["restore", "snapshot"],
                    command_template: "cx restore {name}",
                    description: "Restore a snapshot",
                    needs_name: true,
                    priority: 10,
                },
                Pattern {
                    keywords: vec!["restore", "project"],
                    command_template: "cx restore {name}",
                    description: "Restore project from snapshot",
                    needs_name: true,
                    priority: 9,
                },
                // Template listing
                Pattern {
                    keywords: vec!["list", "templates"],
                    command_template: "cx new --list",
                    description: "List available project templates",
                    needs_name: false,
                    priority: 10,
                },
                Pattern {
                    keywords: vec!["what", "templates"],
                    command_template: "cx new --list",
                    description: "Show available templates",
                    needs_name: false,
                    priority: 9,
                },
                Pattern {
                    keywords: vec!["available", "projects"],
                    command_template: "cx new --list",
                    description: "Show available project types",
                    needs_name: false,
                    priority: 8,
                },
            ],
        }
    }

    /// Match a query against known patterns
    pub fn match_query(&self, query: &str) -> Option<PatternMatch> {
        let query_lower = query.to_lowercase();
        let words: Vec<&str> = query_lower.split_whitespace().collect();

        let mut best_match: Option<(usize, &Pattern, f32)> = None;

        for pattern in &self.patterns {
            let matched_count = pattern
                .keywords
                .iter()
                .filter(|kw| words.iter().any(|w| w.contains(*kw)))
                .count();

            if matched_count == pattern.keywords.len() {
                let confidence = (matched_count as f32 / pattern.keywords.len() as f32)
                    * (pattern.priority as f32 / 10.0);

                if best_match.is_none() || confidence > best_match.as_ref().unwrap().2 {
                    best_match = Some((matched_count, pattern, confidence));
                }
            }
        }

        best_match.map(|(_, pattern, confidence)| PatternMatch {
            command: pattern.command_template.to_string(),
            description: pattern.description.to_string(),
            confidence,
            needs_name: pattern.needs_name,
        })
    }

    /// Extract a potential project name from the query
    pub fn extract_name(&self, query: &str) -> Option<String> {
        let words: Vec<&str> = query.split_whitespace().collect();

        // Look for patterns like "called X", "named X", or quoted strings
        for (i, word) in words.iter().enumerate() {
            if (*word == "called" || *word == "named") && i + 1 < words.len() {
                return Some(words[i + 1].trim_matches('"').trim_matches('\'').to_string());
            }
        }

        // Look for quoted strings
        if let Some(start) = query.find('"') {
            if let Some(end) = query[start + 1..].find('"') {
                return Some(query[start + 1..start + 1 + end].to_string());
            }
        }

        // Look for last word that looks like a name (not a common word)
        let common_words = [
            "a", "an", "the", "create", "make", "new", "project", "app", "with",
            "for", "my", "please", "can", "you", "i", "want", "need", "setup",
            "set", "up", "build", "start", "init", "initialize",
        ];

        for word in words.iter().rev() {
            let clean = word.trim_matches(|c: char| !c.is_alphanumeric() && c != '-' && c != '_');
            if !clean.is_empty() && !common_words.contains(&clean.to_lowercase().as_str()) {
                // Check if it looks like a project name
                if clean.chars().all(|c| c.is_alphanumeric() || c == '-' || c == '_') {
                    return Some(clean.to_string());
                }
            }
        }

        None
    }
}

impl Default for PatternMatcher {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_python_project() {
        let matcher = PatternMatcher::new();
        let result = matcher.match_query("create a python project");
        assert!(result.is_some());
        assert!(result.unwrap().command.contains("cx new python"));
    }

    #[test]
    fn test_react_app() {
        let matcher = PatternMatcher::new();
        let result = matcher.match_query("create a react app");
        assert!(result.is_some());
        assert!(result.unwrap().command.contains("cx new react"));
    }

    #[test]
    fn test_save_work() {
        let matcher = PatternMatcher::new();
        let result = matcher.match_query("save my work");
        assert!(result.is_some());
        assert!(result.unwrap().command.contains("cx save"));
    }

    #[test]
    fn test_extract_name() {
        let matcher = PatternMatcher::new();
        assert_eq!(
            matcher.extract_name("create a python project called my-app"),
            Some("my-app".to_string())
        );
        assert_eq!(
            matcher.extract_name("create react app \"my-frontend\""),
            Some("my-frontend".to_string())
        );
    }
}
