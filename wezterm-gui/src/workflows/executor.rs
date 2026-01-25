//! Workflow execution engine
//!
//! Handles running workflows with:
//! - Variable substitution
//! - Error handling and rollback
//! - Timeout enforcement
//! - Step conditions
//! - Output capture

use super::{StepCondition, Workflow, WorkflowError, WorkflowStep};
use std::collections::HashMap;
use std::io::{BufRead, BufReader};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

/// Result of executing a single step
#[derive(Debug, Clone)]
pub struct StepResult {
    /// Index of the step
    pub step_index: usize,
    /// Whether the step succeeded
    pub success: bool,
    /// Exit code (if available)
    pub exit_code: Option<i32>,
    /// Captured stdout
    pub stdout: Option<String>,
    /// Captured stderr
    pub stderr: Option<String>,
    /// How long the step took
    pub duration: Duration,
    /// Error message (if failed)
    pub error: Option<String>,
    /// Whether the step was skipped
    pub skipped: bool,
}

/// Result of executing a workflow
#[derive(Debug, Clone)]
pub struct ExecutionResult {
    /// Whether the overall execution succeeded
    pub success: bool,
    /// Results for each step
    pub step_results: Vec<StepResult>,
    /// Total execution time
    pub total_duration: Duration,
    /// Captured variables
    pub captured_variables: HashMap<String, String>,
    /// Error message (if failed)
    pub error: Option<String>,
}

/// Callback for execution progress
pub trait ExecutionCallback: Send + Sync {
    /// Called when a step starts
    fn on_step_start(&self, step_index: usize, command: &str);

    /// Called when step output is received
    fn on_step_output(&self, step_index: usize, line: &str, is_stderr: bool);

    /// Called when a step completes
    fn on_step_complete(&self, result: &StepResult);

    /// Called when the workflow completes
    fn on_workflow_complete(&self, result: &ExecutionResult);
}

/// A no-op callback for when no progress reporting is needed
pub struct NoopCallback;

impl ExecutionCallback for NoopCallback {
    fn on_step_start(&self, _: usize, _: &str) {}
    fn on_step_output(&self, _: usize, _: &str, _: bool) {}
    fn on_step_complete(&self, _: &StepResult) {}
    fn on_workflow_complete(&self, _: &ExecutionResult) {}
}

/// Workflow executor
pub struct Executor {
    /// Current working directory
    working_dir: Option<String>,
    /// Environment variables to set
    environment: HashMap<String, String>,
    /// Shell to use for commands
    shell: String,
    /// Shell argument for running commands
    shell_arg: String,
    /// Cancel flag
    cancel_flag: Arc<AtomicBool>,
}

impl Default for Executor {
    fn default() -> Self {
        Self::new()
    }
}

impl Executor {
    /// Create a new executor
    pub fn new() -> Self {
        // Determine shell based on platform
        #[cfg(unix)]
        let (shell, shell_arg) = ("sh".to_string(), "-c".to_string());

        #[cfg(windows)]
        let (shell, shell_arg) = ("cmd".to_string(), "/C".to_string());

        Self {
            working_dir: None,
            environment: HashMap::new(),
            shell,
            shell_arg,
            cancel_flag: Arc::new(AtomicBool::new(false)),
        }
    }

    /// Set the working directory
    pub fn with_working_dir(mut self, dir: &str) -> Self {
        self.working_dir = Some(dir.to_string());
        self
    }

    /// Add environment variables
    pub fn with_env(mut self, env: HashMap<String, String>) -> Self {
        self.environment.extend(env);
        self
    }

    /// Set the shell to use
    pub fn with_shell(mut self, shell: &str, arg: &str) -> Self {
        self.shell = shell.to_string();
        self.shell_arg = arg.to_string();
        self
    }

    /// Get a cancellation handle
    pub fn cancel_handle(&self) -> Arc<AtomicBool> {
        Arc::clone(&self.cancel_flag)
    }

    /// Cancel the current execution
    pub fn cancel(&self) {
        self.cancel_flag.store(true, Ordering::SeqCst);
    }

    /// Check if execution was cancelled
    fn is_cancelled(&self) -> bool {
        self.cancel_flag.load(Ordering::SeqCst)
    }

    /// Execute a workflow
    pub fn execute(
        &mut self,
        workflow: &Workflow,
        variables: HashMap<String, String>,
        callback: &dyn ExecutionCallback,
    ) -> ExecutionResult {
        // Reset cancel flag
        self.cancel_flag.store(false, Ordering::SeqCst);

        let start_time = Instant::now();
        let mut step_results = Vec::new();
        let mut captured_variables = variables.clone();
        let mut last_success = true;

        for (index, step) in workflow.steps.iter().enumerate() {
            // Check for cancellation
            if self.is_cancelled() {
                return ExecutionResult {
                    success: false,
                    step_results,
                    total_duration: start_time.elapsed(),
                    captured_variables,
                    error: Some("Execution cancelled".to_string()),
                };
            }

            // Check step condition
            if !self.should_run_step(step, last_success, &captured_variables) {
                step_results.push(StepResult {
                    step_index: index,
                    success: true,
                    exit_code: None,
                    stdout: None,
                    stderr: None,
                    duration: Duration::ZERO,
                    error: None,
                    skipped: true,
                });
                continue;
            }

            // Substitute variables in command
            let command = workflow.substitute_variables(&step.command, &captured_variables);

            // Notify callback
            callback.on_step_start(index, &command);

            // Apply step delay if configured
            if let Some(delay_ms) = step.delay_ms {
                std::thread::sleep(Duration::from_millis(delay_ms));
            }

            // Execute the step
            let result = self.execute_step(index, step, &command, &captured_variables, callback);

            // Capture output variable if configured
            if let Some(ref var_name) = step.output_variable {
                if let Some(ref stdout) = result.stdout {
                    captured_variables.insert(var_name.clone(), stdout.trim().to_string());
                }
            }

            last_success = result.success;

            // Notify callback
            callback.on_step_complete(&result);

            let should_stop = !result.success && !step.continue_on_error;
            step_results.push(result);

            if should_stop {
                let error = format!("Step {} failed", index);
                let execution_result = ExecutionResult {
                    success: false,
                    step_results,
                    total_duration: start_time.elapsed(),
                    captured_variables,
                    error: Some(error),
                };
                callback.on_workflow_complete(&execution_result);
                return execution_result;
            }
        }

        let execution_result = ExecutionResult {
            success: true,
            step_results,
            total_duration: start_time.elapsed(),
            captured_variables,
            error: None,
        };

        callback.on_workflow_complete(&execution_result);
        execution_result
    }

    /// Check if a step should run based on its condition
    fn should_run_step(
        &self,
        step: &WorkflowStep,
        last_success: bool,
        variables: &HashMap<String, String>,
    ) -> bool {
        match &step.condition {
            None | Some(StepCondition::Always) => true,
            Some(StepCondition::OnSuccess) => last_success,
            Some(StepCondition::OnFailure) => !last_success,
            Some(StepCondition::IfEquals { variable, value }) => {
                variables.get(variable).map_or(false, |v| v == value)
            }
            Some(StepCondition::IfSet { variable }) => {
                variables.get(variable).map_or(false, |v| !v.is_empty())
            }
            Some(StepCondition::IfFileExists { path }) => std::path::Path::new(path).exists(),
            Some(StepCondition::Custom(cmd)) => {
                let status = Command::new(&self.shell)
                    .arg(&self.shell_arg)
                    .arg(cmd)
                    .status();

                status.map_or(false, |s| s.success())
            }
        }
    }

    /// Execute a single step
    fn execute_step(
        &self,
        index: usize,
        step: &WorkflowStep,
        command: &str,
        _variables: &HashMap<String, String>,
        callback: &dyn ExecutionCallback,
    ) -> StepResult {
        let start_time = Instant::now();

        // Build the command
        let mut cmd = Command::new(&self.shell);
        cmd.arg(&self.shell_arg);
        cmd.arg(command);

        // Set working directory
        if let Some(ref dir) = step.working_directory {
            cmd.current_dir(dir);
        } else if let Some(ref dir) = self.working_dir {
            cmd.current_dir(dir);
        }

        // Set environment
        for (key, value) in &self.environment {
            cmd.env(key, value);
        }
        for (key, value) in &step.environment {
            cmd.env(key, value);
        }

        // Configure output capture
        if step.capture_output || !step.background {
            cmd.stdout(Stdio::piped());
            cmd.stderr(Stdio::piped());
        }

        // Spawn the process
        let child_result = cmd.spawn();

        let mut child = match child_result {
            Ok(child) => child,
            Err(e) => {
                return StepResult {
                    step_index: index,
                    success: false,
                    exit_code: None,
                    stdout: None,
                    stderr: None,
                    duration: start_time.elapsed(),
                    error: Some(format!("Failed to spawn: {}", e)),
                    skipped: false,
                };
            }
        };

        // Handle background execution
        if step.background {
            return StepResult {
                step_index: index,
                success: true,
                exit_code: None,
                stdout: None,
                stderr: None,
                duration: start_time.elapsed(),
                error: None,
                skipped: false,
            };
        }

        // Read output with timeout
        let (stdout, stderr, exit_code, error) = self.wait_for_step(
            index,
            &mut child,
            step.timeout,
            step.capture_output,
            callback,
        );

        let success = exit_code.map_or(false, |c| c == 0) && error.is_none();

        StepResult {
            step_index: index,
            success,
            exit_code,
            stdout,
            stderr,
            duration: start_time.elapsed(),
            error,
            skipped: false,
        }
    }

    /// Wait for a step to complete with optional timeout
    fn wait_for_step(
        &self,
        index: usize,
        child: &mut Child,
        timeout: Option<Duration>,
        capture: bool,
        callback: &dyn ExecutionCallback,
    ) -> (Option<String>, Option<String>, Option<i32>, Option<String>) {
        let start_time = Instant::now();

        // Collect output
        let mut stdout_lines = Vec::new();
        let mut stderr_lines = Vec::new();

        // Read stdout in a thread
        if let Some(stdout) = child.stdout.take() {
            let reader = BufReader::new(stdout);
            for line in reader.lines() {
                if self.is_cancelled() {
                    let _ = child.kill();
                    return (None, None, None, Some("Cancelled".to_string()));
                }

                if let Some(t) = timeout {
                    if start_time.elapsed() > t {
                        let _ = child.kill();
                        return (None, None, None, Some("Timeout".to_string()));
                    }
                }

                if let Ok(line) = line {
                    callback.on_step_output(index, &line, false);
                    if capture {
                        stdout_lines.push(line);
                    }
                }
            }
        }

        // Read stderr
        if let Some(stderr) = child.stderr.take() {
            let reader = BufReader::new(stderr);
            for line in reader.lines() {
                if let Ok(line) = line {
                    callback.on_step_output(index, &line, true);
                    if capture {
                        stderr_lines.push(line);
                    }
                }
            }
        }

        // Wait for exit
        let status = match child.wait() {
            Ok(status) => status,
            Err(e) => {
                return (
                    if capture {
                        Some(stdout_lines.join("\n"))
                    } else {
                        None
                    },
                    if capture {
                        Some(stderr_lines.join("\n"))
                    } else {
                        None
                    },
                    None,
                    Some(format!("Wait failed: {}", e)),
                );
            }
        };

        (
            if capture {
                Some(stdout_lines.join("\n"))
            } else {
                None
            },
            if capture {
                Some(stderr_lines.join("\n"))
            } else {
                None
            },
            status.code(),
            None,
        )
    }

    /// Execute a single command (convenience method)
    pub fn run_command(&mut self, command: &str) -> Result<String, WorkflowError> {
        let output = Command::new(&self.shell)
            .arg(&self.shell_arg)
            .arg(command)
            .output()
            .map_err(|e| WorkflowError::ExecutionError(e.to_string()))?;

        if output.status.success() {
            Ok(String::from_utf8_lossy(&output.stdout).to_string())
        } else {
            let stderr = String::from_utf8_lossy(&output.stderr);
            Err(WorkflowError::ExecutionError(stderr.to_string()))
        }
    }
}

/// Builder for executing workflows with custom settings
pub struct ExecutionBuilder<'a> {
    workflow: &'a Workflow,
    variables: HashMap<String, String>,
    working_dir: Option<String>,
    environment: HashMap<String, String>,
    callback: Option<Box<dyn ExecutionCallback + 'a>>,
}

impl<'a> ExecutionBuilder<'a> {
    /// Create a new execution builder
    pub fn new(workflow: &'a Workflow) -> Self {
        Self {
            workflow,
            variables: HashMap::new(),
            working_dir: None,
            environment: HashMap::new(),
            callback: None,
        }
    }

    /// Set a variable value
    pub fn with_variable(mut self, name: &str, value: &str) -> Self {
        self.variables.insert(name.to_string(), value.to_string());
        self
    }

    /// Set multiple variable values
    pub fn with_variables(mut self, vars: HashMap<String, String>) -> Self {
        self.variables.extend(vars);
        self
    }

    /// Set the working directory
    pub fn in_directory(mut self, dir: &str) -> Self {
        self.working_dir = Some(dir.to_string());
        self
    }

    /// Add environment variables
    pub fn with_env(mut self, env: HashMap<String, String>) -> Self {
        self.environment.extend(env);
        self
    }

    /// Set a callback for progress reporting
    pub fn with_callback(mut self, callback: impl ExecutionCallback + 'a) -> Self {
        self.callback = Some(Box::new(callback));
        self
    }

    /// Execute the workflow
    pub fn execute(self) -> ExecutionResult {
        let mut executor = Executor::new();

        if let Some(dir) = self.working_dir {
            executor = executor.with_working_dir(&dir);
        }

        executor = executor.with_env(self.environment);

        let callback: &dyn ExecutionCallback = match &self.callback {
            Some(cb) => cb.as_ref(),
            None => &NoopCallback,
        };

        executor.execute(self.workflow, self.variables, callback)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_simple_execution() {
        let workflow = Workflow::from_commands("Test", vec!["echo hello"]);
        let mut executor = Executor::new();
        let result = executor.execute(&workflow, HashMap::new(), &NoopCallback);

        assert!(result.success);
        assert_eq!(result.step_results.len(), 1);
    }

    #[test]
    fn test_variable_substitution() {
        let mut workflow = Workflow::from_commands("Test", vec!["echo {{message}}"]);
        workflow.add_variable(
            "message",
            super::super::WorkflowVariable::with_default("msg", "hello"),
        );

        let mut vars = HashMap::new();
        vars.insert("message".to_string(), "world".to_string());

        let mut executor = Executor::new();
        let result = executor.execute(&workflow, vars, &NoopCallback);

        assert!(result.success);
    }

    #[test]
    fn test_step_failure() {
        let workflow = Workflow::from_commands("Test", vec!["exit 1", "echo should not run"]);
        let mut executor = Executor::new();
        let result = executor.execute(&workflow, HashMap::new(), &NoopCallback);

        assert!(!result.success);
        assert_eq!(result.step_results.len(), 1);
    }

    #[test]
    fn test_continue_on_error() {
        let mut workflow = Workflow::from_commands("Test", vec!["exit 1", "echo second"]);
        workflow.steps[0].continue_on_error = true;

        let mut executor = Executor::new();
        let result = executor.execute(&workflow, HashMap::new(), &NoopCallback);

        assert!(result.success); // Overall succeeds because we continued
        assert_eq!(result.step_results.len(), 2);
    }

    #[test]
    fn test_execution_builder() {
        let workflow = Workflow::from_commands("Test", vec!["echo {{name}}"]);

        let result = ExecutionBuilder::new(&workflow)
            .with_variable("name", "test")
            .execute();

        assert!(result.success);
    }
}
