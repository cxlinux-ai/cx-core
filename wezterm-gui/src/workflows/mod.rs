//! Workflows module for CX Terminal
//!
//! Workflows are saved sequences of commands that can be:
//! - Created from history
//! - Edited and customized
//! - Executed with variable substitution
//! - Shared and imported

pub mod executor;
pub mod storage;
pub mod ui;

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::Duration;
use uuid::Uuid;

/// A workflow is a saved sequence of commands
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Workflow {
    /// Unique identifier
    pub id: Uuid,
    /// Display name
    pub name: String,
    /// Description of what this workflow does
    pub description: String,
    /// The sequence of steps to execute
    pub steps: Vec<WorkflowStep>,
    /// Variables that can be substituted in commands
    pub variables: HashMap<String, WorkflowVariable>,
    /// Tags for organization
    pub tags: Vec<String>,
    /// When this workflow was created
    pub created_at: DateTime<Utc>,
    /// When this workflow was last modified
    pub updated_at: DateTime<Utc>,
    /// When this workflow was last run
    pub last_run: Option<DateTime<Utc>>,
    /// How many times this workflow has been run
    pub run_count: u32,
    /// Whether this workflow is a favorite
    pub favorite: bool,
    /// Keyboard shortcut (if any)
    pub shortcut: Option<String>,
    /// Author or source
    pub author: Option<String>,
    /// Version for updates
    pub version: String,
}

impl Default for Workflow {
    fn default() -> Self {
        Self {
            id: Uuid::new_v4(),
            name: String::new(),
            description: String::new(),
            steps: Vec::new(),
            variables: HashMap::new(),
            tags: Vec::new(),
            created_at: Utc::now(),
            updated_at: Utc::now(),
            last_run: None,
            run_count: 0,
            favorite: false,
            shortcut: None,
            author: None,
            version: "1.0.0".to_string(),
        }
    }
}

impl Workflow {
    /// Create a new empty workflow
    pub fn new(name: &str) -> Self {
        Self {
            name: name.to_string(),
            ..Default::default()
        }
    }

    /// Create a workflow from a list of commands
    pub fn from_commands(name: &str, commands: Vec<&str>) -> Self {
        let steps = commands
            .into_iter()
            .map(|cmd| WorkflowStep::new(cmd))
            .collect();

        Self {
            name: name.to_string(),
            steps,
            ..Default::default()
        }
    }

    /// Add a step to the workflow
    pub fn add_step(&mut self, step: WorkflowStep) {
        self.steps.push(step);
        self.updated_at = Utc::now();
    }

    /// Remove a step from the workflow
    pub fn remove_step(&mut self, index: usize) -> Option<WorkflowStep> {
        if index < self.steps.len() {
            self.updated_at = Utc::now();
            Some(self.steps.remove(index))
        } else {
            None
        }
    }

    /// Add a variable definition
    pub fn add_variable(&mut self, name: &str, var: WorkflowVariable) {
        self.variables.insert(name.to_string(), var);
        self.updated_at = Utc::now();
    }

    /// Get all variable names used in steps
    pub fn used_variables(&self) -> Vec<String> {
        let mut vars = Vec::new();
        for step in &self.steps {
            for var in Self::extract_variables(&step.command) {
                if !vars.contains(&var) {
                    vars.push(var);
                }
            }
        }
        vars
    }

    /// Extract variable names from a command string
    fn extract_variables(command: &str) -> Vec<String> {
        let mut vars = Vec::new();
        let mut chars = command.chars().peekable();

        while let Some(c) = chars.next() {
            if c == '{' && chars.peek() == Some(&'{') {
                chars.next(); // consume second {
                let mut var_name = String::new();
                while let Some(&c) = chars.peek() {
                    if c == '}' {
                        chars.next();
                        if chars.peek() == Some(&'}') {
                            chars.next();
                            if !var_name.is_empty() {
                                vars.push(var_name);
                            }
                            break;
                        }
                    }
                    var_name.push(chars.next().unwrap());
                }
            }
        }

        vars
    }

    /// Substitute variables in a command
    pub fn substitute_variables(
        &self,
        command: &str,
        overrides: &HashMap<String, String>,
    ) -> String {
        let mut result = command.to_string();

        for (name, var) in &self.variables {
            let placeholder = format!("{{{{{}}}}}", name);
            let value = overrides.get(name).unwrap_or(&var.default_value);
            result = result.replace(&placeholder, value);
        }

        // Also substitute any overrides not in variables
        for (name, value) in overrides {
            let placeholder = format!("{{{{{}}}}}", name);
            result = result.replace(&placeholder, value);
        }

        result
    }

    /// Validate the workflow
    pub fn validate(&self) -> Result<(), WorkflowError> {
        if self.name.is_empty() {
            return Err(WorkflowError::InvalidName("Name cannot be empty".into()));
        }

        if self.steps.is_empty() {
            return Err(WorkflowError::NoSteps);
        }

        // Check that all used variables are defined
        for var in self.used_variables() {
            if !self.variables.contains_key(&var) {
                return Err(WorkflowError::UndefinedVariable(var));
            }
        }

        // Validate each step
        for (i, step) in self.steps.iter().enumerate() {
            if step.command.trim().is_empty() {
                return Err(WorkflowError::EmptyCommand(i));
            }
        }

        Ok(())
    }

    /// Mark as run
    pub fn record_run(&mut self) {
        self.last_run = Some(Utc::now());
        self.run_count += 1;
    }
}

/// A single step in a workflow
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkflowStep {
    /// The command to execute
    pub command: String,
    /// Human-readable description of this step
    pub description: Option<String>,
    /// Whether to wait for this command to succeed before continuing
    pub wait_for_success: bool,
    /// Whether to capture the output of this command
    pub capture_output: bool,
    /// Name to store captured output as (for use in later steps)
    pub output_variable: Option<String>,
    /// Timeout for this step (None = no timeout)
    pub timeout: Option<Duration>,
    /// Whether to continue on error
    pub continue_on_error: bool,
    /// Working directory override
    pub working_directory: Option<String>,
    /// Environment variables to set
    pub environment: HashMap<String, String>,
    /// Condition for running this step
    pub condition: Option<StepCondition>,
    /// Whether to run in background
    pub background: bool,
    /// Delay before executing (in milliseconds)
    pub delay_ms: Option<u64>,
}

impl WorkflowStep {
    /// Create a new step with just a command
    pub fn new(command: &str) -> Self {
        Self {
            command: command.to_string(),
            description: None,
            wait_for_success: true,
            capture_output: false,
            output_variable: None,
            timeout: None,
            continue_on_error: false,
            working_directory: None,
            environment: HashMap::new(),
            condition: None,
            background: false,
            delay_ms: None,
        }
    }

    /// Create a step that captures output
    pub fn with_capture(command: &str, variable_name: &str) -> Self {
        Self {
            command: command.to_string(),
            capture_output: true,
            output_variable: Some(variable_name.to_string()),
            ..Self::new(command)
        }
    }

    /// Set a timeout for this step
    pub fn with_timeout(mut self, timeout: Duration) -> Self {
        self.timeout = Some(timeout);
        self
    }

    /// Set continue on error
    pub fn ignore_errors(mut self) -> Self {
        self.continue_on_error = true;
        self
    }

    /// Add environment variable
    pub fn with_env(mut self, key: &str, value: &str) -> Self {
        self.environment.insert(key.to_string(), value.to_string());
        self
    }

    /// Set working directory
    pub fn in_directory(mut self, dir: &str) -> Self {
        self.working_directory = Some(dir.to_string());
        self
    }

    /// Run in background
    pub fn in_background(mut self) -> Self {
        self.background = true;
        self.wait_for_success = false;
        self
    }
}

impl Default for WorkflowStep {
    fn default() -> Self {
        Self::new("")
    }
}

/// A variable definition for a workflow
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkflowVariable {
    /// Description of what this variable is for
    pub description: String,
    /// Default value
    pub default_value: String,
    /// Whether this variable is required
    pub required: bool,
    /// Type hint for the UI
    pub var_type: VariableType,
    /// Validation pattern (regex)
    pub validation: Option<String>,
    /// Possible values (for select type)
    pub options: Option<Vec<String>>,
}

impl Default for WorkflowVariable {
    fn default() -> Self {
        Self {
            description: String::new(),
            default_value: String::new(),
            required: false,
            var_type: VariableType::String,
            validation: None,
            options: None,
        }
    }
}

impl WorkflowVariable {
    /// Create a new required variable
    pub fn required(description: &str) -> Self {
        Self {
            description: description.to_string(),
            required: true,
            ..Default::default()
        }
    }

    /// Create a variable with a default value
    pub fn with_default(description: &str, default: &str) -> Self {
        Self {
            description: description.to_string(),
            default_value: default.to_string(),
            ..Default::default()
        }
    }

    /// Create a select variable with options
    pub fn select(description: &str, options: Vec<&str>) -> Self {
        let default_value = options.first().map(|s| s.to_string()).unwrap_or_default();
        Self {
            description: description.to_string(),
            var_type: VariableType::Select,
            options: Some(options.into_iter().map(String::from).collect()),
            default_value,
            ..Default::default()
        }
    }

    /// Validate a value against this variable's constraints
    pub fn validate(&self, value: &str) -> Result<(), String> {
        if self.required && value.is_empty() {
            return Err("Value is required".to_string());
        }

        if let Some(ref pattern) = self.validation {
            let re = regex::Regex::new(pattern)
                .map_err(|e| format!("Invalid validation pattern: {}", e))?;
            if !re.is_match(value) {
                return Err(format!("Value does not match pattern: {}", pattern));
            }
        }

        if let Some(ref options) = self.options {
            if !value.is_empty() && !options.contains(&value.to_string()) {
                return Err(format!("Value must be one of: {:?}", options));
            }
        }

        Ok(())
    }
}

/// Type hint for workflow variables
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Default)]
pub enum VariableType {
    /// Free-form string
    #[default]
    String,
    /// File path
    Path,
    /// Directory path
    Directory,
    /// Select from options
    Select,
    /// Boolean (yes/no)
    Boolean,
    /// Integer number
    Integer,
    /// Password (hidden in UI)
    Password,
}

/// Condition for running a step
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum StepCondition {
    /// Always run (default)
    Always,
    /// Only run if previous step succeeded
    OnSuccess,
    /// Only run if previous step failed
    OnFailure,
    /// Run if variable equals value
    IfEquals { variable: String, value: String },
    /// Run if variable is not empty
    IfSet { variable: String },
    /// Run if file exists
    IfFileExists { path: String },
    /// Custom condition (shell command that returns 0 for true)
    Custom(String),
}

impl Default for StepCondition {
    fn default() -> Self {
        Self::Always
    }
}

/// Errors that can occur with workflows
#[derive(Debug, Clone)]
pub enum WorkflowError {
    /// Workflow name is invalid
    InvalidName(String),
    /// Workflow has no steps
    NoSteps,
    /// Variable is used but not defined
    UndefinedVariable(String),
    /// Step has empty command
    EmptyCommand(usize),
    /// IO error
    IoError(String),
    /// Serialization error
    SerializationError(String),
    /// Execution error
    ExecutionError(String),
    /// Step timed out
    Timeout(usize),
    /// Step failed
    StepFailed { step: usize, message: String },
    /// Workflow not found
    NotFound(String),
}

impl std::fmt::Display for WorkflowError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidName(msg) => write!(f, "Invalid workflow name: {}", msg),
            Self::NoSteps => write!(f, "Workflow has no steps"),
            Self::UndefinedVariable(var) => write!(f, "Undefined variable: {}", var),
            Self::EmptyCommand(idx) => write!(f, "Step {} has empty command", idx),
            Self::IoError(msg) => write!(f, "IO error: {}", msg),
            Self::SerializationError(msg) => write!(f, "Serialization error: {}", msg),
            Self::ExecutionError(msg) => write!(f, "Execution error: {}", msg),
            Self::Timeout(idx) => write!(f, "Step {} timed out", idx),
            Self::StepFailed { step, message } => write!(f, "Step {} failed: {}", step, message),
            Self::NotFound(id) => write!(f, "Workflow not found: {}", id),
        }
    }
}

impl std::error::Error for WorkflowError {}

impl From<std::io::Error> for WorkflowError {
    fn from(e: std::io::Error) -> Self {
        Self::IoError(e.to_string())
    }
}

impl From<serde_json::Error> for WorkflowError {
    fn from(e: serde_json::Error) -> Self {
        Self::SerializationError(e.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_workflow_creation() {
        let wf = Workflow::new("Test Workflow");
        assert_eq!(wf.name, "Test Workflow");
        assert!(wf.steps.is_empty());
    }

    #[test]
    fn test_workflow_from_commands() {
        let wf = Workflow::from_commands("Build", vec!["cargo build", "cargo test"]);
        assert_eq!(wf.steps.len(), 2);
        assert_eq!(wf.steps[0].command, "cargo build");
        assert_eq!(wf.steps[1].command, "cargo test");
    }

    #[test]
    fn test_variable_extraction() {
        let wf = Workflow::from_commands("Test", vec!["echo {{name}}", "cd {{dir}}"]);
        let vars = wf.used_variables();
        assert!(vars.contains(&"name".to_string()));
        assert!(vars.contains(&"dir".to_string()));
    }

    #[test]
    fn test_variable_substitution() {
        let mut wf = Workflow::from_commands("Test", vec!["echo {{message}}"]);
        wf.add_variable(
            "message",
            WorkflowVariable::with_default("The message", "hello"),
        );

        let overrides = HashMap::new();
        let result = wf.substitute_variables(&wf.steps[0].command, &overrides);
        assert_eq!(result, "echo hello");

        let mut overrides = HashMap::new();
        overrides.insert("message".to_string(), "world".to_string());
        let result = wf.substitute_variables(&wf.steps[0].command, &overrides);
        assert_eq!(result, "echo world");
    }

    #[test]
    fn test_workflow_validation() {
        let empty = Workflow::new("");
        assert!(empty.validate().is_err());

        let no_steps = Workflow::new("Test");
        assert!(matches!(no_steps.validate(), Err(WorkflowError::NoSteps)));

        let valid = Workflow::from_commands("Test", vec!["echo test"]);
        assert!(valid.validate().is_ok());
    }
}
